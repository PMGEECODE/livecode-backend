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
    try:
        # 1. Log sanitized DATABASE_URL
        db_url = str(engine.url)
        # Handle asyncpg urls which usually contain the password
        if ":" in db_url and "@" in db_url:
            # Simple sanitization: keep driver and host, hide credentials
            parts = db_url.split("@")
            prefix = parts[0].split(":")[0] + "://****:****"
            db_url_sanitized = f"{prefix}@{parts[1]}"
        else:
            db_url_sanitized = db_url
            
        logger.info(f"🔍 Checking database connection: {db_url_sanitized}")

        # 2. Test Connection
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection established successfully.")

            # 3. Check Migrations
            def get_migration_status(connection):
                alembic_cfg = Config("alembic.ini")
                script_dir = script.ScriptDirectory.from_config(alembic_cfg)
                context = migration.MigrationContext.configure(connection)
                return context.get_current_revision(), script_dir.get_current_head()

            current_rev, head_rev = await conn.run_sync(get_migration_status)
            
            if current_rev == head_rev:
                logger.info(f"🚀 Database migrations are UP TO DATE (Revision: {current_rev})")
            else:
                logger.warning(f"⚠️  Database migrations are OUT OF SYNC! (Current: {current_rev}, Head: {head_rev})")
                
    except Exception as e:
        logger.error(f"❌ Database health check failed: {str(e)}")

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to Livecode Technologies API"}
