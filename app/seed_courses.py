import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.models.course import Course
from app.core.config import settings

COURSES_DATA = [
    {
        "title": "Saccolink Reconciliation for IT and Support Staff",
        "slug": "saccolink-reconciliation",
        "start_date": "28 Sep",
        "end_date": "2 Oct",
        "duration": "5 days",
        "location": "Kisumu, Kenya",
        "price_kes": 110000.0,
        "price_usd": 1500.0,
        "category": "Short Courses",
        "image_url": "https://images.unsplash.com/photo-1551288049-bbbda5366391?auto=format&fit=crop&q=80&w=400",
    },
    {
        "title": "English for Non-Native Speakers Course",
        "slug": "english-non-native",
        "start_date": "1 Jun",
        "end_date": "5 Jun",
        "duration": "5 days",
        "location": "Addis Ababa, Ethiopia",
        "price_kes": None,
        "price_usd": 3900.0,
        "category": "Short Courses",
        "image_url": "https://images.unsplash.com/photo-1543269865-cbf427effbad?auto=format&fit=crop&q=80&w=400",
    },
    {
        "title": "Community Health Promotion Strategies and Interventions",
        "slug": "community-health-promotion",
        "start_date": "18 May",
        "end_date": "22 May",
        "duration": "5 days",
        "location": "Kisumu, Kenya",
        "price_kes": 110000.0,
        "price_usd": 1500.0,
        "category": "Short Courses",
        "image_url": "https://images.unsplash.com/photo-1576091160550-2173dba999ef?auto=format&fit=crop&q=80&w=400",
    },
    {
        "title": "Forest Fire Management and Prevention Training Course",
        "slug": "forest-fire-management",
        "start_date": "26 Oct",
        "end_date": "6 Nov",
        "duration": "10 days",
        "location": "Nakuru, Kenya",
        "price_kes": 190000.0,
        "price_usd": 2700.0,
        "category": "Short Courses",
        "image_url": "https://images.unsplash.com/photo-1582139329536-e7284fece509?auto=format&fit=crop&q=80&w=400",
    },
    {
        "title": "AWS Certified Solutions Architect Associate Training",
        "slug": "aws-certified-solutions-architect",
        "start_date": "20 Sep",
        "end_date": "1 Oct",
        "duration": "10 days",
        "location": "Cairo, Egypt",
        "price_kes": None,
        "price_usd": 7700.0,
        "category": "Short Courses",
        "image_url": "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&q=80&w=400",
    },
    {
        "title": "Customer Segmentation and Churn Prediction",
        "slug": "customer-segmentation-churn",
        "start_date": "7 Sep",
        "end_date": "11 Sep",
        "duration": "5 days",
        "location": "Kigali, Rwanda",
        "price_kes": None,
        "price_usd": 1850.0,
        "category": "Short Courses",
        "image_url": "https://images.unsplash.com/photo-1551288049-bbbda5366391?auto=format&fit=crop&q=80&w=400",
    },
    {
        "title": "Sector-Specific Licensing and Regulatory Oversight Training",
        "slug": "sector-specific-licensing",
        "start_date": "8 Jun",
        "end_date": "19 Jun",
        "duration": "10 days",
        "location": "Kampala, Uganda",
        "price_kes": None,
        "price_usd": 3700.0,
        "category": "Short Courses",
        "image_url": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?auto=format&fit=crop&q=80&w=400",
    },
    {
        "title": "Performance Benchmarking in Water and Sanitation Utilities",
        "slug": "performance-benchmarking-water",
        "start_date": "13 Jul",
        "end_date": "17 Jul",
        "duration": "5 days",
        "location": "Zanzibar, Tanzania",
        "price_kes": None,
        "price_usd": 2100.0,
        "category": "Short Courses",
        "image_url": "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&q=80&w=400",
    },
]

async def seed():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        for course_data in COURSES_DATA:
            # Check if exists
            result = await session.execute(select(Course).where(Course.slug == course_data["slug"]))
            if result.scalar_one_or_none():
                print(f"Course {course_data['slug']} already exists, skipping...")
                continue
            
            course = Course(**course_data)
            session.add(course)
        
        await session.commit()
        print("Seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed())
