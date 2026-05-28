from typing import Optional
from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator
from uuid import UUID
from datetime import datetime


class TrustedPartnerBase(BaseModel):
    name: str
    logo_url: str
    website_url: Optional[str] = None
    display_order: int = 0
    is_active: bool = True


class TrustedPartnerCreate(TrustedPartnerBase):
    name: str
    logo_url: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        if len(v) > 200:
            raise ValueError("name must be 200 characters or fewer")
        return v

    @field_validator("logo_url")
    @classmethod
    def logo_url_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("logo_url must not be blank")
        return v


class TrustedPartnerUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name must not be blank")
            if len(v) > 200:
                raise ValueError("name must be 200 characters or fewer")
        return v


class TrustedPartner(TrustedPartnerBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
