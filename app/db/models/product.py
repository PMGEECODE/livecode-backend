from sqlalchemy import Column, String, Float, Boolean, JSON, DateTime, Text
from sqlalchemy.sql import func
from app.db.base_class import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid

class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    short_description = Column(String(500), nullable=True)
    price = Column(Float, nullable=False, default=0.0)
    currency = Column(String(10), nullable=False, default="USD")
    category = Column(String(100), nullable=False)
    image_url = Column(String(1024), nullable=True)
    image_gallery = Column(JSON, nullable=True, default=[]) # List of image URLs
    features = Column(JSON, nullable=False, default=[])
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
