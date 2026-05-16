
import asyncio
import json
import re
from datetime import datetime, date
from typing import Optional, List, Any

from app.db.session import SessionLocal
from app.crud.course import course as crud_course
from sqlalchemy import select
from app.db.models.course import Course
from sqlalchemy.orm import selectinload

async def debug_sync():
    async with SessionLocal() as db:
        result = await db.execute(
            select(Course)
            .order_by(Course.id.desc())
            .limit(1)
            .options(selectinload(Course.schedules))
        )
        course = result.scalars().first()
        if not course:
            print("No course found")
            return

        print(f"DEBUGGING COURSE: {course.title} (Slug: {course.slug})")
        print(f"Current Date: {date.today()}")
        
        print("\nSCHEDULES:")
        for s in course.schedules:
            print(f" - {s.date_range} | {s.location} | KES {s.price_kes}")
            
        print("\nSYNCING...")
        synced_course = crud_course._sync_event_properties(course)
        
        try:
            blocks = json.loads(synced_course.curriculum)
            for block in blocks:
                if block.get('type') == 'section_header':
                    print(f"\nHeader: {block.get('title')}")
                if block.get('type') == 'table':
                    print("Table Rows:")
                    for row in block.get('rows', []):
                        print(f"   {row}")
        except Exception as e:
            print(f"JSON Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_sync())
