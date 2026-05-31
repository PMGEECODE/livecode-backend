import uuid
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(40), nullable=True)
    occupation = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    source = Column(String(80), nullable=True)
    unsubscribe_token = Column(String(80), nullable=False, unique=True, index=True)
    welcome_email_sent = Column(Boolean, nullable=False, default=False)
    last_digest_sent_at = Column(DateTime(timezone=True), nullable=True)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NewsletterDelivery(Base):
    __tablename__ = "newsletter_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscriber_email = Column(String(255), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    html_body = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    scheduled_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
