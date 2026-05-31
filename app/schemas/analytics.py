import re
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


ALLOWED_ANALYTICS_EVENTS = {
    "course_viewed",
    "course_register_clicked",
    "training_calendar_opened",
    "trainer_application_started",
    "trainer_application_submitted",
    "product_viewed",
    "product_preview_clicked",
    "callback_requested",
}

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")


def _clean_optional_text(value: Optional[str], max_length: int) -> Optional[str]:
    if value is None:
        return None
    value = _CONTROL_RE.sub("", str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_length] or None


class AnalyticsEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_name: str
    page_path: Optional[str] = None
    page_title: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    entity_title: Optional[str] = None
    referrer: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        value = _clean_optional_text(value, 80) or ""
        if not _EVENT_RE.match(value) or value not in ALLOWED_ANALYTICS_EVENTS:
            raise ValueError("Unsupported analytics event.")
        return value

    @field_validator("page_path", "referrer")
    @classmethod
    def validate_path_like(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value, 500)

    @field_validator("page_title", "entity_title")
    @classmethod
    def validate_title(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value, 300)

    @field_validator("entity_type", "session_id")
    @classmethod
    def validate_short_text(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value, 80)

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value, 160)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not value:
            return None
        safe: Dict[str, Any] = {}
        for key, item in list(value.items())[:20]:
            safe_key = _clean_optional_text(str(key), 60)
            if not safe_key:
                continue
            if isinstance(item, (str, int, float, bool)) or item is None:
                safe[safe_key] = _clean_optional_text(item, 300) if isinstance(item, str) else item
        return safe or None


class AnalyticsEventResponse(BaseModel):
    id: UUID
    event_name: str
    page_path: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    entity_title: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
