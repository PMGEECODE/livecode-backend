import re
from datetime import datetime
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
    welcome_email_sent: bool
    last_digest_sent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class NewsletterThemeBase(BaseModel):
    name: str
    primary_color: str
    secondary_color: str
    bg_color: str
    card_bg: str
    text_color: str
    heading_color: str
    font_family: Optional[str] = "'Outfit', 'Inter', -apple-system, sans-serif"
    template_layout: Optional[str] = "classic_card"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = _clean(value, 100)
        if len(value) < 2:
            raise ValueError("Theme name is required.")
        return value

    @field_validator("primary_color", "secondary_color", "bg_color", "card_bg", "text_color", "heading_color")
    @classmethod
    def validate_hex_color(cls, value: str) -> str:
        value = value.strip()
        if not re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", value):
            raise ValueError("Must be a valid hex color starting with #")
        return value

    @field_validator("template_layout")
    @classmethod
    def validate_layout(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return "classic_card"
        allowed = ["classic_card", "minimalist", "modern_split", "compact_digest"]
        if value not in allowed:
            raise ValueError(f"Template layout must be one of: {', '.join(allowed)}")
        return value


class NewsletterThemeCreate(NewsletterThemeBase):
    pass


class NewsletterThemeUpdate(BaseModel):
    name: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    bg_color: Optional[str] = None
    card_bg: Optional[str] = None
    text_color: Optional[str] = None
    heading_color: Optional[str] = None
    font_family: Optional[str] = None
    template_layout: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = _clean(value, 100)
        if len(value) < 2:
            raise ValueError("Theme name is required.")
        return value

    @field_validator("primary_color", "secondary_color", "bg_color", "card_bg", "text_color", "heading_color")
    @classmethod
    def validate_hex_color(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", value):
            raise ValueError("Must be a valid hex color starting with #")
        return value

    @field_validator("template_layout")
    @classmethod
    def validate_layout(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        allowed = ["classic_card", "minimalist", "modern_split", "compact_digest"]
        if value not in allowed:
            raise ValueError(f"Template layout must be one of: {', '.join(allowed)}")
        return value


class NewsletterThemeResponse(NewsletterThemeBase):
    id: UUID
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
