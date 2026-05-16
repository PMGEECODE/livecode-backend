from typing import Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class BlogPostBase(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None

class BlogPostCreate(BlogPostBase):
    title: str
    slug: str
    content: str

class BlogPostUpdate(BlogPostBase):
    pass

class BlogPostInDBBase(BlogPostBase):
    id: UUID
    published_date: Optional[datetime] = None

    class Config:
        from_attributes = True

class BlogPost(BlogPostInDBBase):
    pass
