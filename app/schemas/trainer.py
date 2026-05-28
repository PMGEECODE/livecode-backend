import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from uuid import UUID
from datetime import datetime


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
    referee1_email: Optional[str] = None

    referee2_name: Optional[str] = None
    referee2_speciality: Optional[str] = None
    referee2_phone: Optional[str] = None
    referee2_email: Optional[str] = None

    referee3_name: Optional[str] = None
    referee3_speciality: Optional[str] = None
    referee3_phone: Optional[str] = None
    referee3_email: Optional[str] = None


class TrainerApplicationCreate(TrainerApplicationBase):
    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Full name is required.")
        if len(v) < 3 or len(v) > 200:
            raise ValueError("Full name must be between 3 and 200 characters.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Phone number is required.")
        # Simple digits + optional + symbol phone validation
        if not re.match(r"^\+?[0-9\s\-()]{7,25}$", v):
            raise ValueError("Invalid phone number format.")
        return v

    @field_validator("dob")
    @classmethod
    def validate_dob(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Date of birth is required.")
        # Simple ISO regex (yyyy-mm-dd)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Date of birth must be in YYYY-MM-DD format.")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Gender is required.")
        return v

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Country is required.")
        return v

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("City is required.")
        return v

    @field_validator("specialization")
    @classmethod
    def validate_specialization(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Area(s) of specialization is required.")
        return v

    @field_validator("cv_url")
    @classmethod
    def validate_cv_url(cls, v: str) -> str:
        v = v.strip()
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
