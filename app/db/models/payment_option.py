from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.db.base_class import Base


class PaymentOptionSetting(Base):
    __tablename__ = "payment_option_setting"

    provider = Column(String(40), primary_key=True)
    label = Column(String(120), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    disabled_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
