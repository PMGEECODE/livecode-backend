from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    # Pre-ping every connection before use — drops silently stale/broken conns
    pool_pre_ping=True,
    # Recycle connections after 5 minutes to avoid "connection closed" from idle timeouts
    pool_recycle=300,
    # 5 persistent + 10 overflow = 15 max concurrent connections
    pool_size=5,
    max_overflow=10,
    # Fail fast (10 s) so the app returns 503 instead of hanging for 30 s
    pool_timeout=10,
    # asyncpg: TCP connect + statement timeout both set to 30 s
    connect_args={
        "timeout": 30,          # TCP/TLS handshake timeout (seconds)
        "command_timeout": 60,  # Per-query execution timeout (seconds)
        "ssl": False,
    },
)

SessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
