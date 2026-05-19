import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.base_class import Base
from app.db.models.course import Course
from app.db.models.registration import CourseRegistration
from app.schemas.registration import RegistrationCreate
from app.crud.registration import create_registration
import uuid

async def main():
    engine = create_async_engine("postgresql+asyncpg://postgres:.7447_GEE@localhost/livecode_db", echo=False)
    SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        course_id = uuid.uuid4()
        c = Course(id=course_id, title="Test", slug="test2", category="test")
        db.add(c)
        await db.commit()

        payload = RegistrationCreate(
            course_id=str(course_id),
            course_title="Test",
            first_name="John",
            last_name="Doe",
            email="john@doe.com",
            registration_type="individual",
            phone="+254712345678",
            how_heard="Test"
        )
        try:
            reg = await create_registration(db=db, payload=payload)
            print("SUCCESS:", reg.id)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("ERROR:", str(e))

if __name__ == "__main__":
    asyncio.run(main())
