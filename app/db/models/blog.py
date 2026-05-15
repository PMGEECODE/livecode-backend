from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.db.base_class import Base

class BlogPost(Base):
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    content = Column(Text, nullable=False)
    author = Column(String, index=True, nullable=True)
    published_date = Column(DateTime(timezone=True), server_default=func.now())
    image_url = Column(String, nullable=True)
