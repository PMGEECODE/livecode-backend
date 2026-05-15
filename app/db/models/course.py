from sqlalchemy import Column, Integer, String, Text, Float
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class Course(Base):
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    curriculum = Column(Text, nullable=True)
    category = Column(String, index=True, nullable=False)
    duration = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    location = Column(String, nullable=True)
    price_kes = Column(Float, nullable=True)
    price_usd = Column(Float, nullable=True)
    image_url = Column(String, nullable=True)
    
    schedules = relationship("Schedule", back_populates="course", cascade="all, delete-orphan")
