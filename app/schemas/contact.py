from typing import Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime

class ContactBase(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    is_resolved: Optional[bool] = False

class ContactCreate(ContactBase):
    name: str
    email: str
    phone: str
    subject: str
    message: str

class ContactUpdate(ContactBase):
    pass

class ContactInDBBase(ContactBase):
    id: UUID
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class Contact(ContactInDBBase):
    pass
