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

    def __init__(
        self,
        *,
        full_name=None,
        email=None,
        phone=None,
        occupation=None,
        source=None,
        unsubscribe_token=None,
        is_active=True,
        welcome_email_sent=False,
        last_digest_sent_at=None,
        unsubscribed_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.full_name = full_name
        self.email = email
        self.phone = phone
        self.occupation = occupation
        self.source = source
        self.unsubscribe_token = unsubscribe_token
        self.is_active = is_active
        self.welcome_email_sent = welcome_email_sent
        self.last_digest_sent_at = last_digest_sent_at
        self.unsubscribed_at = unsubscribed_at


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

    def __init__(
        self,
        *,
        subscriber_email=None,
        subject=None,
        html_body=None,
        status="pending",
        error_message=None,
        attempts=0,
        sent_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.subscriber_email = subscriber_email
        self.subject = subject
        self.html_body = html_body
        self.status = status
        self.error_message = error_message
        self.attempts = attempts
        self.sent_at = sent_at


class NewsletterTheme(Base):
    __tablename__ = "newsletter_themes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    primary_color = Column(String(7), nullable=False)
    secondary_color = Column(String(7), nullable=False)
    bg_color = Column(String(7), nullable=False)
    card_bg = Column(String(7), nullable=False)
    text_color = Column(String(7), nullable=False)
    heading_color = Column(String(7), nullable=False)
    font_family = Column(String(255), nullable=False, default="'Outfit', 'Inter', -apple-system, sans-serif")
    template_layout = Column(String(50), nullable=False, default="classic_card")
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __init__(
        self,
        *,
        name=None,
        primary_color=None,
        secondary_color=None,
        bg_color=None,
        card_bg=None,
        text_color=None,
        heading_color=None,
        font_family="'Outfit', 'Inter', -apple-system, sans-serif",
        template_layout="classic_card",
        is_active=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.name = name
        self.primary_color = primary_color
        self.secondary_color = secondary_color
        self.bg_color = bg_color
        self.card_bg = card_bg
        self.text_color = text_color
        self.heading_color = heading_color
        self.font_family = font_family
        self.template_layout = template_layout
        self.is_active = is_active
