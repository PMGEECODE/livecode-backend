from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class Schedule(Base):
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("course.id"), nullable=False)
    date_range = Column(String, nullable=False)  # e.g., "18 May – 29 May"
    location = Column(String, nullable=False)    # e.g., "Kisumu", "Nairobi", "Online"
    mode = Column(String, nullable=False)        # "physical" or "virtual"
    price_kes = Column(Float, nullable=True)
    price_usd = Column(Float, nullable=True)
    year = Column(Integer, default=2026)
    registration_url = Column(String, nullable=True)

    course = relationship("Course", back_populates="schedules")
