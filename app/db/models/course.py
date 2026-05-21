import uuid
from sqlalchemy import Column, String, Text, Float, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base

class Course(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String, index=True, nullable=False)
    sub_category = Column(String, index=True, nullable=True)
    image_url = Column(String, nullable=True)
    
    # Relationships
    logistics = relationship("CourseLogistics", back_populates="course", uselist=False, cascade="all, delete-orphan")
    curriculum_blocks = relationship("CourseBlock", back_populates="course", cascade="all, delete-orphan", order_by="CourseBlock.order_index")
    schedules = relationship("Schedule", back_populates="course", cascade="all, delete-orphan")

class CourseLogistics(Base):
    __tablename__ = "course_logistics"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("course.id"), nullable=False, unique=True)
    duration = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    location = Column(String, nullable=True)
    price_kes = Column(Float, nullable=True)
    price_usd = Column(Float, nullable=True)

    course = relationship("Course", back_populates="logistics")

class CourseBlock(Base):
    __tablename__ = "course_block"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("course.id"), nullable=False, index=True)
    type = Column(String, nullable=False)  # paragraph, list, table, subheading, etc.
    content = Column(JSON, nullable=False) # Stores the block data
    order_index = Column(Integer, nullable=False)

    course = relationship("Course", back_populates="curriculum_blocks")
