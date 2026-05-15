from typing import Optional, List
from pydantic import BaseModel

class ScheduleBase(BaseModel):
    date_range: Optional[str] = None
    location: Optional[str] = None
    mode: Optional[str] = None
    price_kes: Optional[float] = None
    price_usd: Optional[float] = None
    year: Optional[int] = 2026
    registration_url: Optional[str] = None

class ScheduleCreate(ScheduleBase):
    date_range: str
    location: str
    mode: str

class ScheduleUpdate(ScheduleBase):
    pass

class Schedule(ScheduleBase):
    id: int
    course_id: int

    class Config:
        from_attributes = True

class CourseBase(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    curriculum: Optional[str] = None
    category: Optional[str] = None
    duration: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    price_kes: Optional[float] = None
    price_usd: Optional[float] = None
    image_url: Optional[str] = None

class CourseCreate(CourseBase):
    title: str
    slug: str
    category: str
    schedules: Optional[List[ScheduleCreate]] = None

class CourseUpdate(CourseBase):
    schedules: Optional[List[ScheduleCreate]] = None

class CourseInDBBase(CourseBase):
    id: Optional[int] = None

    class Config:
        from_attributes = True

class Course(CourseInDBBase):
    schedules: List[Schedule] = []
