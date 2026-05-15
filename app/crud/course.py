from typing import Optional, List, Union, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi.encoders import jsonable_encoder
from app.crud.base import CRUDBase
from app.db.models.course import Course
from app.schemas.course import CourseCreate, CourseUpdate

from app.db.models.schedule import Schedule

class CRUDCourse(CRUDBase[Course, CourseCreate, CourseUpdate]):
    async def get(self, db: AsyncSession, id: Any) -> Optional[Course]:
        result = await db.execute(
            select(Course)
            .filter(Course.id == id)
            .options(selectinload(Course.schedules))
        )
        return result.scalars().first()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[Course]:
        result = await db.execute(
            select(Course)
            .offset(skip)
            .limit(limit)
            .options(selectinload(Course.schedules))
        )
        return list(result.scalars().all())

    async def get_by_slug(self, db: AsyncSession, *, slug: str) -> Optional[Course]:
        result = await db.execute(
            select(Course)
            .filter(Course.slug == slug)
            .options(selectinload(Course.schedules))
        )
        return result.scalars().first()

    async def create(self, db: AsyncSession, *, obj_in: CourseCreate) -> Course:
        obj_in_data = jsonable_encoder(obj_in)
        schedules_data = obj_in_data.pop("schedules", [])
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        await db.flush() # Get the ID
        
        for schedule_data in schedules_data:
            schedule = Schedule(**schedule_data, course_id=db_obj.id)
            db.add(schedule)
            
        course_id = db_obj.id
        await db.commit()
        return await self.get(db, id=course_id)

    async def update(
        self, db: AsyncSession, *, db_obj: Course, obj_in: Union[CourseUpdate, Dict[str, Any]]
    ) -> Course:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
            
        schedules_data = update_data.pop("schedules", None)
        
        # Update standard fields
        for field in update_data:
            if hasattr(db_obj, field):
                setattr(db_obj, field, update_data[field])
        db.add(db_obj)
        
        # Update schedules if provided
        if schedules_data is not None:
            # Simple approach: delete all and re-create
            from sqlalchemy import delete
            await db.execute(delete(Schedule).where(Schedule.course_id == db_obj.id))
            for schedule_data in schedules_data:
                schedule = Schedule(**schedule_data, course_id=db_obj.id)
                db.add(schedule)
                
        course_id = db_obj.id
        await db.commit()
        return await self.get(db, id=course_id)

course = CRUDCourse(Course)
