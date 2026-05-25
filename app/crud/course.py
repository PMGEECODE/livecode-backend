from typing import Optional, List, Union, Dict, Any
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi.encoders import jsonable_encoder
from app.crud.base import CRUDBase
from app.db.models.course import Course, CourseLogistics, CourseBlock
from app.db.models.schedule import Schedule
from app.schemas.course import CourseCreate, CourseUpdate

import json
import re
from datetime import datetime, timedelta

class CRUDCourse(CRUDBase[Course, CourseCreate, CourseUpdate]):
    def _normalize_slug(self, slug: str) -> str:
        normalized = slug.strip().lower()
        normalized = re.sub(r"[\s_]+", "-", normalized)
        normalized = re.sub(r"-{2,}", "-", normalized)
        return normalized.strip("-")

    def _parse_datetime(self, date_str: str, end_of_day: bool = False) -> Optional[datetime]:
        if not date_str:
            return None
        clean_str = re.sub(r'([0-1]\d|2[0-3]):([0-5]\d)\s*[ap]m', r'\1:\2', date_str, flags=re.I)
        formats = [
            "%m-%d-%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M",
            "%m-%d-%Y %I:%M %p", "%d-%m-%Y %I:%M %p",
            "%m-%d-%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", 
            "%b %d, %Y", "%d %b, %Y", "%d %B, %Y", "%B %d, %Y"
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(clean_str.strip(), fmt)
                if end_of_day and "%H" not in fmt and "%I" not in fmt:
                    dt = dt.replace(hour=23, minute=59, second=59)
                return dt
            except ValueError:
                continue
        return None

    def _sync_event_properties(self, course: Course):
        if not course or not course.schedules:
            return course
        
        try:
            now = datetime.now()
            
            # 1. Find the next upcoming schedule
            upcoming = []
            for s in course.schedules:
                parts = re.split(r'\s+(?:-|–)\s+', s.date_range)
                dt_end = self._parse_datetime(parts[-1], end_of_day=True)
                if dt_end and dt_end >= now:
                    dt_start = self._parse_datetime(parts[0])
                    if not dt_start and len(parts) > 1:
                        year_match = re.search(r'\d{4}', parts[-1])
                        if year_match:
                            dt_start = self._parse_datetime(f"{parts[0]} {year_match.group()}")
                    
                    upcoming.append({
                        "start": dt_start or dt_end,
                        "end": dt_end,
                        "sched": s
                    })
            
            if not upcoming:
                return course
                
            upcoming.sort(key=lambda x: x["start"])
            best = upcoming[0]
            start_dt, end_dt, next_sched = best["start"], best["end"], best["sched"]
            
            # 2. Update CourseLogistics
            if course.logistics:
                course.logistics.start_date = start_dt.strftime("%m-%d-%Y")
                course.logistics.end_date = end_dt.strftime("%m-%d-%Y")
                course.logistics.location = next_sched.location
                course.logistics.price_kes = next_sched.price_kes
                course.logistics.price_usd = next_sched.price_usd

            # 3. Update the "Event Properties" table block in curriculum_blocks
            def format_dt(d: datetime): return d.strftime("%m-%d-%Y")
            def format_full(d: datetime): return f"{format_dt(d)} 12:00 am"

            for i, block in enumerate(course.curriculum_blocks):
                is_target_table = False
                
                # Case A: Table follows an "Event Properties" header
                if block.type in ['section_header', 'subheading'] and 'event properties' in str(block.content.get('title') or block.content.get('text', '')).lower():
                    if i + 1 < len(course.curriculum_blocks) and course.curriculum_blocks[i+1].type == 'table':
                        # We tag it for the next block iteration
                        continue
                
                # Case B: Table itself contains "Event Date" in first column
                if block.type == 'table':
                    rows = block.content.get('rows', [])
                    # We check if this table looks like Event Properties
                    if any('event date' in str(row[0]).lower() for row in rows if row):
                        is_target_table = True
                
                if is_target_table:
                    rows = block.content.get('rows', [])
                    new_rows = []
                    for row in rows:
                        if not row or len(row) < 2: 
                            new_rows.append(row)
                            continue
                        
                        label = str(row[0]).lower().strip().strip(':')
                        if label == 'event date':
                            row[1] = format_full(start_dt)
                        elif label == 'event end date':
                            row[1] = format_full(end_dt)
                        elif label == 'cut off date':
                            row[1] = format_dt(start_dt - timedelta(days=4))
                        elif label == 'individual price':
                            row[1] = f"KES: {int(next_sched.price_kes or 0):,} USD: {int(next_sched.price_usd or 0):,}"
                        elif label == 'location':
                            row[1] = next_sched.location
                        elif label == 'registered':
                            row[1] = "0"
                        new_rows.append(row)
                    block.content['rows'] = new_rows
                    
        except Exception as e:
            # Silently fail sync to prevent course loading failure
            pass
            
        return course

    async def get(self, db: AsyncSession, id: Any) -> Optional[Course]:
        result = await db.execute(
            select(Course)
            .filter(Course.id == id)
            .options(
                selectinload(Course.schedules),
                selectinload(Course.logistics),
                selectinload(Course.curriculum_blocks)
            )
        )
        db_obj = result.scalars().first()
        if db_obj:
            return self._sync_event_properties(db_obj)
        return None

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
        sub_category: Optional[str] = None,
        random: bool = False,
        summary: bool = False,
    ) -> List[Course]:
        query = select(Course)
        if category:
            query = query.filter(func.lower(Course.category) == category.strip().lower())
        if sub_category:
            query = query.filter(func.lower(Course.sub_category) == sub_category.strip().lower())

        if random:
            from sqlalchemy import func as sa_func
            query = query.order_by(sa_func.random())
        else:
            query = query.offset(skip)

        options = [
            selectinload(Course.schedules),
            selectinload(Course.logistics)
        ]
        if not summary:
            options.append(selectinload(Course.curriculum_blocks))

        result = await db.execute(
            query
            .limit(limit)
            .options(*options)
        )
        return list(result.scalars().all())

    async def get_by_slug(self, db: AsyncSession, *, slug: str) -> Optional[Course]:
        normalized_slug = self._normalize_slug(slug)
        result = await db.execute(
            select(Course)
            .filter(
                (Course.slug == slug)
                | (func.lower(Course.slug) == normalized_slug)
                | (func.lower(Course.slug) == slug.strip().lower())
            )
            .options(
                selectinload(Course.schedules),
                selectinload(Course.logistics),
                selectinload(Course.curriculum_blocks)
            )
        )
        db_obj = result.scalars().first()
        if db_obj:
            return self._sync_event_properties(db_obj)
        return None

    async def create(self, db: AsyncSession, *, obj_in: CourseCreate) -> Course:
        obj_in_data = jsonable_encoder(obj_in)
        schedules_data = obj_in_data.pop("schedules", None) or []
        logistics_data = obj_in_data.pop("logistics", None)
        curriculum_blocks_data = obj_in_data.pop("curriculum_blocks", None) or []
        
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        await db.flush() # Get the ID
        
        # Create logistics
        if logistics_data:
            log_data = logistics_data.model_dump() if hasattr(logistics_data, "model_dump") else logistics_data
            log_data["course_id"] = db_obj.id
            logistics = CourseLogistics(**log_data)
            db.add(logistics)
            
        # Create blocks
        for i, block_data in enumerate(curriculum_blocks_data):
            b_data = block_data.model_dump() if hasattr(block_data, "model_dump") else block_data
            b_data["course_id"] = db_obj.id
            b_data["order_index"] = i
            block = CourseBlock(**b_data)
            db.add(block)
            
        # Create schedules
        for schedule_data in schedules_data:
            s_data = schedule_data.model_dump() if hasattr(schedule_data, "model_dump") else schedule_data
            s_data["course_id"] = db_obj.id
            schedule = Schedule(**s_data)
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
        logistics_data = update_data.pop("logistics", None)
        curriculum_blocks_data = update_data.pop("curriculum_blocks", None)
        
        # Update standard fields
        for field in update_data:
            if hasattr(db_obj, field):
                setattr(db_obj, field, update_data[field])
        db.add(db_obj)
        
        # Update logistics
        if logistics_data is not None:
            log_data = logistics_data.model_dump() if hasattr(logistics_data, "model_dump") else logistics_data
            if not db_obj.logistics:
                log_data["course_id"] = db_obj.id
                db_obj.logistics = CourseLogistics(**log_data)
            else:
                for field, value in log_data.items():
                    setattr(db_obj.logistics, field, value)
            db.add(db_obj.logistics)

        # Update curriculum blocks
        if curriculum_blocks_data is not None:
            await db.execute(delete(CourseBlock).where(CourseBlock.course_id == db_obj.id))
            for i, block_data in enumerate(curriculum_blocks_data):
                b_data = block_data.model_dump() if hasattr(block_data, "model_dump") else block_data
                b_data["course_id"] = db_obj.id
                b_data["order_index"] = i
                block = CourseBlock(**b_data)
                db.add(block)

        # Update schedules if provided
        if schedules_data is not None:
            await db.execute(delete(Schedule).where(Schedule.course_id == db_obj.id))
            for schedule_data in schedules_data:
                s_data = schedule_data.model_dump() if hasattr(schedule_data, "model_dump") else schedule_data
                s_data["course_id"] = db_obj.id
                schedule = Schedule(**s_data)
                db.add(schedule)
                
        course_id = db_obj.id
        await db.commit()
        return await self.get(db, id=course_id)

course = CRUDCourse(Course)
