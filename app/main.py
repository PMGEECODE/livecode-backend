import logging
import contextlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from alembic.config import Config
from alembic import script
from alembic.runtime import migration

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import engine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_db_health():
    import asyncio

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

from app.core.redis import redis_manager

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await check_db_health()
    await redis_manager.init()
    yield
    # Shutdown logic (if any)
    await redis_manager.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

from fastapi.middleware.gzip import GZipMiddleware
# Enable GZIP compression for responses > 1000 bytes to reduce payload size and network latency
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Set all CORS enabled origins
origins = [str(origin).strip() for origin in settings.cors_origins if str(origin).strip()]

# Regex to allow local development on any port and Vercel subdomains (including branch/preview deployments)
cors_regex = r"^https://.*\.vercel\.app$|^http://localhost(:\d+)?$|^http://127\.0\.0\.1(:\d+)?$"

if "*" in origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=cors_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.core.limiter import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(api_router, prefix=settings.API_V1_STR)

import os
from fastapi import Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={"year": datetime.now().year}
    )

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        accept_header = request.headers.get("accept", "")
        
        # If it's a direct API request expecting JSON, return JSON.
        # But if a user visits ANY 404 route in a browser (which accepts text/html), show the custom page.
        if "text/html" not in accept_header and request.url.path.startswith(settings.API_V1_STR):
            return JSONResponse({"detail": exc.detail}, status_code=404)
        
        # Serve the HTML template
        return templates.TemplateResponse(
            request=request, 
            name="404.html", 
            context={"year": datetime.now().year}, 
            status_code=404
        )
    
    # Fallback to default JSON error for all other exception types
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

from fastapi.responses import FileResponse

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

