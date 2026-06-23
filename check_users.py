import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.base_class import Base
from app.db.models.user import User
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        print("Existing Users:")
        for u in users:
            print(f"- Email: {u.email}, Name: {u.full_name}, Superuser: {u.is_superuser}, Active: {u.is_active}")

if __name__ == "__main__":
    asyncio.run(main())
