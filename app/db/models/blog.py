import uuid
from sqlalchemy import Column, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base

class BlogPost(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    content = Column(Text, nullable=False)
    author = Column(String, index=True, nullable=True)
    published_date = Column(DateTime(timezone=True), server_default=func.now())
    image_url = Column(String, nullable=True)
