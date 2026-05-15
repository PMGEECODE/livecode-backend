from sqlalchemy import Column, Integer, String, Text
from app.db.base_class import Base

class Service(Base):
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    icon = Column(String, nullable=True)  # e.g., font-awesome class or image path
