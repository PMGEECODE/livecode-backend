import uuid
from sqlalchemy import Column, String, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base

class Schedule(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("course.id"), nullable=False)
    date_range = Column(String, nullable=False)  # e.g., "18 May – 29 May"
    location = Column(String, nullable=False)    # e.g., "Kisumu", "Nairobi", "Online"
    mode = Column(String, nullable=False)        # "physical" or "virtual"
    price_kes = Column(Float, nullable=True)
    price_usd = Column(Float, nullable=True)
    year = Column(Integer, default=2026)
    registration_url = Column(String, nullable=True)

    course = relationship("Course", back_populates="schedules")
