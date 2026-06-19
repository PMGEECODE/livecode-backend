import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.base import Base, Course, CourseLogistics, Schedule
from app.core.config import settings
from app.seed_courses import COURSES_DATA
import json

async def main():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    
    print("Creating all tables via Base.metadata.create_all...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        print("Seeding standard courses...")
        for course_data in COURSES_DATA:
            result = await session.execute(select(Course).where(Course.slug == course_data["slug"]))
            if result.scalar_one_or_none():
                print(f"Course {course_data['slug']} already exists, skipping...")
                continue
            
            # Extract logistics fields
            logistics_data = {
                "duration": course_data.get("duration"),
                "start_date": course_data.get("start_date"),
                "end_date": course_data.get("end_date"),
                "location": course_data.get("location"),
                "price_kes": course_data.get("price_kes"),
                "price_usd": course_data.get("price_usd"),
            }
            
            course = Course(
                title=course_data["title"],
                slug=course_data["slug"],
                category=course_data["category"],
                image_url=course_data.get("image_url")
            )
            session.add(course)
            await session.flush() # get course.id
            
            logistics = CourseLogistics(
                course_id=course.id,
                **logistics_data
            )
            session.add(logistics)
            
            # Create a default schedule
            schedule = Schedule(
                course_id=course.id,
                date_range=f"{course_data.get('start_date', 'TBD')} - {course_data.get('end_date', 'TBD')}",
                location=course_data.get("location", "TBA"),
                mode="physical",
                price_kes=course_data.get("price_kes"),
                price_usd=course_data.get("price_usd"),
                year=2026
            )
            session.add(schedule)
            
        print("Seeding detailed course...")
        # Detailed course
        from app.clear_and_seed_course import TITLE, SLUG, CATEGORY, DURATION, LOCATION, PRICE_KES, PRICE_USD, CURRICULUM
        result = await session.execute(select(Course).where(Course.slug == SLUG))
        if not result.scalar_one_or_none():
            course = Course(
                title=TITLE,
                slug=SLUG,
                category=CATEGORY,
                image_url="https://images.unsplash.com/photo-1599507593499-a3f7f7d9a2cc?auto=format&fit=crop&q=80&w=1200"
            )
            session.add(course)
            await session.flush()
            
            logistics = CourseLogistics(
                course_id=course.id,
                duration=DURATION,
                location=LOCATION,
                price_kes=PRICE_KES,
                price_usd=PRICE_USD
            )
            session.add(logistics)
            
            schedule_data = {
                "course_id": course.id,
                "date_range": "18 May – 29 May",
                "location": "Nairobi, Kenya",
                "mode": "physical",
                "price_kes": PRICE_KES,
                "price_usd": PRICE_USD,
                "year": 2026
            }
            schedule = Schedule(**schedule_data)
            session.add(schedule)
            
        await session.commit()
        print("Database initialization and seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
