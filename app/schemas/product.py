from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

class ProductBase(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    description: str
    short_description: Optional[str] = Field(None, max_length=500)
    price: float = Field(0.0, ge=0.0)
    currency: str = Field("USD", max_length=10)
    category: str = Field(..., max_length=100)
    image_url: Optional[str] = Field(None, max_length=1024)
    image_gallery: Optional[List[str]] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)
    is_active: bool = True
    preview_url: Optional[str] = Field(None, max_length=1024)
    view_url: Optional[str] = Field(None, max_length=1024)

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=500)
    price: Optional[float] = Field(None, ge=0.0)
    currency: Optional[str] = Field(None, max_length=10)
    category: Optional[str] = Field(None, max_length=100)
    image_url: Optional[str] = Field(None, max_length=1024)
    image_gallery: Optional[List[str]] = None
    features: Optional[List[str]] = None
    is_active: Optional[bool] = None
    preview_url: Optional[str] = Field(None, max_length=1024)
    view_url: Optional[str] = Field(None, max_length=1024)

class ProductInDBBase(ProductBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Product(ProductInDBBase):
    pass
