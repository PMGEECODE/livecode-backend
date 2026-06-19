import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.base import Course
from app.core.config import settings

async def main():
    print("Database URI:", settings.SQLALCHEMY_DATABASE_URI)
    try:
        engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Course))
            courses = result.scalars().all()
            print(f"Found {len(courses)} courses:")
            for c in courses:
                print(f"ID: {c.id} | Slug: {c.slug} | Image URL: {c.image_url}")
    except Exception as e:
        print("Error connecting/querying:", e)

if __name__ == "__main__":
    asyncio.run(main())
