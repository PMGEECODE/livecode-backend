
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

async def find_course():
    async with SessionLocal() as db:
        result = await db.execute(
            select(Course)
            .options(selectinload(Course.schedules))
        )
        courses = result.scalars().all()
        print(f"Checking {len(courses)} courses...")
        
        for c in courses:
            if not c.curriculum: continue
            if "05-18-2026 12:00 am" in c.curriculum:
                print(f"\nFOUND MATCHING COURSE: {c.title} (Slug: {c.slug})")
                print(f"Schedules count: {len(c.schedules)}")
                # Check what sync would do
                synced = crud_course._sync_event_properties(c)
                if "05-16-2026" in synced.curriculum:
                    print("SYNC SUCCESS: Found 05-16 in synced curriculum")
                else:
                    print("SYNC FAILED: Could not find 05-16 in synced curriculum")

if __name__ == "__main__":
    asyncio.run(find_course())
