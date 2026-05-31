import uuid
from sqlalchemy import Column, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.types import JSON

from app.db.base_class import Base


class ProductAnalyticsEvent(Base):
    __tablename__ = "product_analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_name = Column(String(80), nullable=False, index=True)
    page_path = Column(String(500), nullable=True, index=True)
    page_title = Column(String(300), nullable=True)
    entity_type = Column(String(80), nullable=True, index=True)
    entity_id = Column(String(160), nullable=True, index=True)
    entity_title = Column(String(300), nullable=True)
    referrer = Column(String(500), nullable=True)
    session_id = Column(String(80), nullable=True, index=True)
    metadata_json = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    user_agent = Column(Text, nullable=True)
    ip_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __init__(
        self,
        *,
        event_name=None,
        page_path=None,
        page_title=None,
        entity_type=None,
        entity_id=None,
        entity_title=None,
        referrer=None,
        session_id=None,
        metadata_json=None,
        user_agent=None,
        ip_hash=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.event_name = event_name
        self.page_path = page_path
        self.page_title = page_title
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.entity_title = entity_title
        self.referrer = referrer
        self.session_id = session_id
        self.metadata_json = metadata_json
        self.user_agent = user_agent
        self.ip_hash = ip_hash
