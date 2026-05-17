import uuid
from sqlalchemy import Column, String, Text, DateTime, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base

class Contact(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, index=True, nullable=False)
    email = Column(String, index=True, nullable=False)
    company = Column(String, nullable=True)
    phone = Column(String, nullable=False)
    subject = Column(String, index=True, nullable=False)
    message = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
