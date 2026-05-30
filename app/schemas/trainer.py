import re
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from uuid import UUID


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_TAG_RE = re.compile(r"<[^>]*>")
_PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{7,25}$")
_SAFE_FILENAME_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"\.(pdf|doc|docx)$",
    re.IGNORECASE,
)


def _clean_text(value: str, *, max_length: int, field_name: str) -> str:
    value = _CONTROL_CHARS_RE.sub("", value)
    value = _HTML_TAG_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer.")
    return value


class TrainerApplicationBase(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    alternate_phone: Optional[str] = None
    dob: str
    gender: str
    country: str
    city: str
    specialization: str
    other_specialization: Optional[str] = None
    cv_url: str
    cover_letter_url: Optional[str] = None

    # Referees
    referee1_name: Optional[str] = None
    referee1_speciality: Optional[str] = None
    referee1_phone: Optional[str] = None
    referee1_email: Optional[EmailStr] = None

    referee2_name: Optional[str] = None
    referee2_speciality: Optional[str] = None
    referee2_phone: Optional[str] = None
    referee2_email: Optional[EmailStr] = None

    referee3_name: Optional[str] = None
    referee3_speciality: Optional[str] = None
    referee3_phone: Optional[str] = None
    referee3_email: Optional[EmailStr] = None


class TrainerApplicationCreate(TrainerApplicationBase):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = _clean_text(v, max_length=200, field_name="Full name")
        if not v:
            raise ValueError("Full name is required.")
        if len(v) < 3:
            raise ValueError("Full name must be between 3 and 200 characters.")
        return v

    @field_validator("alternate_phone", "referee1_phone", "referee2_phone", "referee3_phone")
    @classmethod
    def validate_optional_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = _clean_text(v, max_length=25, field_name="Phone number")
        if not v:
            return None
        if not _PHONE_RE.match(v):
            raise ValueError("Invalid phone number format.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = _clean_text(v, max_length=25, field_name="Phone number")
        if not v:
            raise ValueError("Phone number is required.")
        if not _PHONE_RE.match(v):
            raise ValueError("Invalid phone number format.")
        return v

    @field_validator("dob")
    @classmethod
    def validate_dob(cls, v: str) -> str:
        v = _clean_text(v, max_length=10, field_name="Date of birth")
        if not v:
            raise ValueError("Date of birth is required.")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Date of birth must be in YYYY-MM-DD format.")
        try:
            dob = date.fromisoformat(v)
        except ValueError:
            raise ValueError("Date of birth is invalid.")
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if dob >= today:
            raise ValueError("Date of birth must be in the past.")
        if age < 18 or age > 100:
            raise ValueError("Applicant age must be between 18 and 100 years.")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        v = _clean_text(v, max_length=40, field_name="Gender")
        if not v:
            raise ValueError("Gender is required.")
        allowed = {"male", "female", "prefer not to say"}
        if v.lower() not in allowed:
            raise ValueError("Invalid gender value.")
        return v

    @field_validator("country", "city")
    @classmethod
    def validate_location(cls, v: str) -> str:
        v = _clean_text(v, max_length=100, field_name="Location")
        if not v:
            raise ValueError("Country and city are required.")
        return v

    @field_validator(
        "other_specialization",
        "referee1_name",
        "referee1_speciality",
        "referee2_name",
        "referee2_speciality",
        "referee3_name",
        "referee3_speciality",
    )
    @classmethod
    def validate_optional_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = _clean_text(v, max_length=300, field_name="Optional text field")
        return v or None

    @field_validator("referee1_email", "referee2_email", "referee3_email", mode="before")
    @classmethod
    def blank_referee_email_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("specialization")
    @classmethod
    def validate_specialization(cls, v: str) -> str:
        v = _clean_text(v, max_length=1500, field_name="Area(s) of specialization")
        if not v:
            raise ValueError("Area(s) of specialization is required.")
        return v

    @field_validator("cv_url", "cover_letter_url")
    @classmethod
    def validate_document_filename(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = _clean_text(v, max_length=80, field_name="Document filename")
        if not v:
            return None
        if not _SAFE_FILENAME_RE.match(v):
            raise ValueError("Invalid uploaded document filename.")
        return v

    @field_validator("cv_url")
    @classmethod
    def require_cv_url(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("CV is required.")
        return v


class TrainerApplicationUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.strip().lower()
        allowed = ["pending", "approved", "declined", "archived"]
        if v not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(allowed)}")
        return v


class TrainerApplicationResponse(TrainerApplicationBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
