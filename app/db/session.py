from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,

    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    pool_timeout=10,
    connect_args={
        "timeout": 30,
        "command_timeout": 60,
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
