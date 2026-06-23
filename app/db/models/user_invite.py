import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base

class UserInvite(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, index=True, nullable=False, unique=True)
    role = Column(String, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        email: str,
        role: str,
        token: str,
        is_used: bool = False,
        expires_at: datetime,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if id is not None:
            self.id = id
        self.email = email
        self.role = role
        self.token = token
        self.is_used = is_used
        self.expires_at = expires_at
