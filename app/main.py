import asyncio
import contextlib
from datetime import datetime
import logging
import os

from alembic import script
from alembic.config import Config
from alembic.runtime import migration
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, TimeoutError as SATimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.limiter import limiter
from app.core.upload_security import upload_root
from app.core.redis import redis_manager
from app.db.session import engine
from app.services.newsletter_worker import newsletter_worker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_db_health():
    db_url = str(engine.url)
    if ":" in db_url and "@" in db_url:
        parts = db_url.split("@")
        prefix = parts[0].split(":")[0] + "://****:****"
        db_url_sanitized = f"{prefix}@{parts[1]}"
    else:
        db_url_sanitized = db_url

    logger.info("🔍 Checking database connection: %s", db_url_sanitized)

    last_exc: Exception | None = None
    for attempt in range(1, 4):          # up to 3 attempts
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                logger.info("✅ Database connection established successfully.")

                def get_migration_status(connection):
                    alembic_cfg = Config("alembic.ini")
                    script_dir = script.ScriptDirectory.from_config(alembic_cfg)
                    context = migration.MigrationContext.configure(connection)
                    return context.get_current_revision(), script_dir.get_current_head()

                current_rev, head_rev = await conn.run_sync(get_migration_status)

                if current_rev == head_rev:
                    logger.info("🚀 Database migrations are UP TO DATE (Revision: %s)", current_rev)
                else:
                    logger.warning(
                        "⚠️  Database migrations are OUT OF SYNC! (Current: %s, Head: %s)",
                        current_rev, head_rev,
                    )
            return  # success — exit the retry loop

        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                wait = attempt * 3   # 3 s, 6 s
                logger.warning(
                    "⚠️  DB connect attempt %d/3 failed (%s). Retrying in %d s…",
                    attempt, repr(exc), wait,
                )
                await asyncio.sleep(wait)

    logger.error("❌ Database health check failed after 3 attempts: %s", repr(last_exc))

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await check_db_health()
    await redis_manager.init()
    newsletter_stop_event: asyncio.Event | None = None
    newsletter_task: asyncio.Task | None = None
    if settings.NEWSLETTER_WORKER_ENABLED:
        newsletter_stop_event = asyncio.Event()
        newsletter_task = asyncio.create_task(newsletter_worker(newsletter_stop_event))
    yield
    # Shutdown logic (if any)
    if newsletter_stop_event and newsletter_task:
        newsletter_stop_event.set()
        try:
            await asyncio.wait_for(newsletter_task, timeout=10)
        except asyncio.TimeoutError:
            newsletter_task.cancel()
    await redis_manager.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Enable GZIP compression for responses > 1000 bytes to reduce payload size and network latency
app.add_middleware(GZipMiddleware, minimum_size=1000)

def get_allowed_cors_origins() -> list[str]:
    origins = [str(origin).strip().rstrip("/") for origin in settings.cors_origins if str(origin).strip()]
    if any(origin == "*" for origin in origins):
        raise RuntimeError(
            "BACKEND_CORS_ORIGINS must list exact allowed origins. Wildcard '*' is not allowed."
        )
    return origins


allowed_cors_origins = get_allowed_cors_origins()
if not allowed_cors_origins:
    logger.warning("No CORS origins configured. Browser requests from other domains will be blocked.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Database connectivity exception handlers ─────────────────────────────────
# asyncpg raises TimeoutError / CancelledError when it cannot establish or
# acquire a connection within the configured timeout.  SQLAlchemy surfaces
# these as OperationalError.  None of these are user errors — return 503 so
# clients can retry, and log at ERROR level for observability.
@app.exception_handler(asyncio.TimeoutError)
async def asyncio_timeout_handler(request: Request, exc: asyncio.TimeoutError):
    logger.error("DB connection timed out for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable. Please try again in a moment."},
        headers={"Retry-After": "5"},
    )

@app.exception_handler(OperationalError)
async def sqlalchemy_operational_handler(request: Request, exc: OperationalError):
    logger.error("DB operational error for %s %s: %s", request.method, request.url.path, repr(exc))
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable. Please try again in a moment."},
        headers={"Retry-After": "5"},
    )

@app.exception_handler(SATimeoutError)
async def sqlalchemy_timeout_handler(request: Request, exc: SATimeoutError):
    logger.error("DB timeout for %s %s: %s", request.method, request.url.path, repr(exc))
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable. Please try again in a moment."},
        headers={"Retry-After": "5"},
    )

# ─────────────────────────────────────────────────────────────────────────────

app.include_router(api_router, prefix=settings.API_V1_STR)

# Ensure restricted upload directory exists. It is NOT publicly mounted via StaticFiles.
# Files are served only through validated API endpoints.
os.makedirs(upload_root(), exist_ok=True)

@app.get("/static/uploads/{slug}/{filename}", include_in_schema=False)
async def legacy_static_redirect(slug: str, filename: str):
    """
    Backward-compatible redirect for image URLs stored in the DB before the
    secure /media endpoint was introduced.  The redirect target goes through
    the validated media router which enforces path- and extension-checks.
    """
    return RedirectResponse(
        url=f"{settings.API_V1_STR}/media/uploads/{slug}/{filename}",
        status_code=301,
    )

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={"year": datetime.now().year}
    )

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    accept_header = request.headers.get("accept", "")
    
    # If the browser accepts HTML, serve HTML templates
    if "text/html" in accept_header:
        if exc.status_code == 404:
            return templates.TemplateResponse(
                request=request, 
                name="404.html", 
                context={"year": datetime.now().year}, 
                status_code=404
            )
        else:
            # Determine Title and detail description for error page
            title = "An Error Occurred"
            detail_msg = exc.detail
            
            if exc.status_code == 401:
                title = "Not Authenticated"
                if not detail_msg or detail_msg == "Not authenticated":
                    detail_msg = "You are not authenticated to view this page. Please log in first."
            elif exc.status_code == 403:
                title = "Access Forbidden"
                if not detail_msg:
                    detail_msg = "You do not have the necessary permissions to access this resource."
            elif exc.status_code == 500:
                title = "Internal Server Error"
                if not detail_msg:
                    detail_msg = "An internal server error occurred. Please try again later."
            
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={
                    "status_code": exc.status_code,
                    "title": title,
                    "detail": detail_msg,
                    "year": datetime.now().year
                },
                status_code=exc.status_code
            )
            
    # Fallback to default JSON error for all other requests (APIs/JSON-expecting requests)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    file_path = os.path.join(os.path.dirname(__file__), "..", "static", "favicon.ico")
    if not os.path.exists(file_path):
        return {"message": "Favicon not found"}
    return FileResponse(file_path, media_type="image/x-icon", headers={"Cache-Control": "public, max-age=31536000"})

@app.get("/robots.txt", include_in_schema=False)
async def robots():
    file_path = os.path.join(os.path.dirname(__file__), "..", "static", "robots.txt")
    if not os.path.exists(file_path):
        return {"message": "robots.txt not found"}
    return FileResponse(file_path, media_type="text/plain")
