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

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await check_db_health()
    yield
    # Shutdown logic (if any)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

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

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to Livecode Technologies API"}
