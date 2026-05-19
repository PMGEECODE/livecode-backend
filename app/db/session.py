from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    # Validate connections before use — drops stale connections silently
    pool_pre_ping=True,
    # Recycle connections after 10 minutes to prevent remote-DB timeouts
    pool_recycle=600,
    # Keep 5 persistent connections; allow 10 overflow under burst load
    pool_size=5,
    max_overflow=10,
    # Wait up to 30 s for a free connection before raising
    pool_timeout=30,
    # asyncpg-level connect timeout (10 s) — prevents indefinite hangs.
    # ssl=False: skip SSL negotiation; the remote DB does not have SSL enabled.
    # Without this, asyncpg tries SSL first, hangs on the handshake, and raises
    # CancelledError / TimeoutError instead of a clean connection refused.
    connect_args={"timeout": 10, "ssl": False},
)

SessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
