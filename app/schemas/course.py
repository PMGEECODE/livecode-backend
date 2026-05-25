from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict
from uuid import UUID

# --- Schedule Schemas ---
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
    id: UUID
    course_id: UUID

    model_config = ConfigDict(from_attributes=True)

# --- Course Block Schemas ---
class CourseBlockBase(BaseModel):
    type: str
    content: Any  # JSON data
    order_index: int

class CourseBlockCreate(CourseBlockBase):
    pass

class CourseBlock(CourseBlockBase):
    id: UUID
    course_id: UUID

    model_config = ConfigDict(from_attributes=True)

# --- Course Logistics Schemas ---
class CourseLogisticsBase(BaseModel):
    duration: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    price_kes: Optional[float] = None
    price_usd: Optional[float] = None

class CourseLogisticsCreate(CourseLogisticsBase):
    pass

class CourseLogistics(CourseLogisticsBase):
    id: UUID
    course_id: UUID

    model_config = ConfigDict(from_attributes=True)

# --- Course Schemas ---
class CourseBase(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    image_url: Optional[str] = None

class CourseCreate(CourseBase):
    title: str
    slug: str
    category: str
    logistics: Optional[CourseLogisticsCreate] = None
    curriculum_blocks: Optional[List[CourseBlockCreate]] = None
    schedules: Optional[List[ScheduleCreate]] = None

class CourseUpdate(CourseBase):
    logistics: Optional[CourseLogisticsCreate] = None
    curriculum_blocks: Optional[List[CourseBlockCreate]] = None
    schedules: Optional[List[ScheduleCreate]] = None

class CourseInDBBase(CourseBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)

class Course(CourseInDBBase):
    logistics: Optional[CourseLogistics] = None
    curriculum_blocks: List[CourseBlock] = []
    schedules: List[Schedule] = []

class CourseSummary(CourseInDBBase):
    logistics: Optional[CourseLogistics] = None
    schedules: List[Schedule] = []

