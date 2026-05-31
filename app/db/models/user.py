import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class User(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)

    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    role = Column(String, default="user", nullable=True)
    status = Column(String, default="active", nullable=True)
    phone = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String, nullable=True)
    is_verified = Column(Boolean(), default=False, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        full_name: str | None = None,
        email: str | None = None,
        hashed_password: str | None = None,
        is_active: bool = True,
        is_superuser: bool = False,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        role: str | None = "user",
        status: str | None = "active",
        phone: str | None = None,
        bio: str | None = None,
        avatar_url: str | None = None,
        is_verified: bool | None = False,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        last_login: datetime | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if id is not None:
            self.id = id
        self.full_name = full_name
        self.email = email
        self.hashed_password = hashed_password
        self.is_active = is_active
        self.is_superuser = is_superuser
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.status = status
        self.phone = phone
        self.bio = bio
        self.avatar_url = avatar_url
        self.is_verified = is_verified
        if created_at is not None:
            self.created_at = created_at
        if updated_at is not None:
            self.updated_at = updated_at
        if last_login is not None:
            self.last_login = last_login
