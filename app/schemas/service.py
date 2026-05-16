from typing import Optional
from pydantic import BaseModel
from uuid import UUID

class ServiceBase(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None

class ServiceCreate(ServiceBase):
    title: str
    slug: str
    description: str

class ServiceUpdate(ServiceBase):
    pass

class ServiceInDBBase(ServiceBase):
    id: UUID

    class Config:
        from_attributes = True

class Service(ServiceInDBBase):
    pass
