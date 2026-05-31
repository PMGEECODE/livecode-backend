import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_RE = re.compile(r"<[^>]*>")
_PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{7,30}$")


def _clean(value: str, max_length: int) -> str:
    value = _CONTROL_RE.sub("", value)
    value = _HTML_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_length]


class NewsletterSubscribe(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    occupation: str
    source: Optional[str] = "footer"

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = _clean(value, 200)
        if len(value) < 2:
            raise ValueError("Full name is required.")
        return value

    @field_validator("occupation")
    @classmethod
    def validate_occupation(cls, value: str) -> str:
        value = _clean(value, 200)
        if len(value) < 2:
            raise ValueError("Occupation is required.")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = _clean(value, 40)
        if not value:
            return None
        if not _PHONE_RE.match(value):
            raise ValueError("Invalid phone number.")
        return value

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _clean(value, 80) or "footer"


class NewsletterSubscriberResponse(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    occupation: str
    source: Optional[str] = None
    is_active: bool
    unsubscribe_token: str

    model_config = ConfigDict(from_attributes=True)
