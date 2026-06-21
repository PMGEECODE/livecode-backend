from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class SupportSessionCreate(BaseModel):
    user_name: str = Field(..., min_length=2, max_length=100)
    user_email: EmailStr
    topic: str = Field("general", min_length=2, max_length=50)

class SupportSessionResponse(BaseModel):
    session_id: UUID
    user_name: str
    user_email: str
    topic: str
    status: str
    created_at: datetime
    agent_takeover: Optional[bool] = False
    agent_name: Optional[str] = None


class SupportMessageCreate(BaseModel):
    sender: str = Field(..., pattern="^(user|agent)$")
    message: str = Field(..., min_length=1, max_length=1000)

class SupportMessageResponse(BaseModel):
    id: UUID
    sender: str
    message: str
    created_at: datetime


class SupportTypingPayload(BaseModel):
    typing: bool
    sender: str = Field(..., pattern="^(user|agent)$")
    agent_name: Optional[str] = None
