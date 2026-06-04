from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
import re

def sanitize_html(value: str) -> str:
    if not isinstance(value, str):
        return value
    # Simple regex to strip HTML tags
    return re.sub(r'<[^>]*>', '', value).strip()

class GroupMember(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=30)
    title: Optional[str] = Field(None, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def sanitize_inputs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    data[k] = sanitize_html(v)
        return data

class RegistrationCreate(BaseModel):
    # Course context
    course_id: Optional[str] = None
    course_title: str = Field(..., min_length=2, max_length=500)
    schedule_date: Optional[str] = Field(None, max_length=200)
    schedule_location: Optional[str] = Field(None, max_length=300)
    registration_type: str = Field("individual", pattern=r"^(individual|group)$")

    # Personal details
    title: Optional[str] = Field(None, max_length=20)
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    gender: Optional[str] = Field(None, pattern=r"^(Male|Female|Other|)$")
    organization: Optional[str] = Field(None, max_length=300)
    department: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=30)
    email: EmailStr
    official_email: Optional[EmailStr] = None
    country: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)

    # Additional info
    how_heard: Optional[str] = Field(None, max_length=300)
    accommodation: Optional[bool] = None
    airport_pickup: Optional[bool] = None
    additional_info: Optional[str] = Field(None, max_length=1000)

    # Group specific
    group_size: Optional[str] = Field(None, max_length=10)
    group_members: Optional[List[GroupMember]] = None

    # Currency selection (USD or KES)
    currency: Optional[str] = Field("USD", max_length=10)

    # Controlling email dispatch on submission (default to "Offline" for backward compatibility)
    payment_method: Optional[str] = Field("Offline", max_length=50)

    @model_validator(mode="before")
    @classmethod
    def sanitize_inputs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    data[k] = sanitize_html(v)
        return data

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not re.match(r"^[\+\d\s\-\(\)]{6,30}$", v):
            raise ValueError("Invalid phone number format")
        return v

    model_config = {"extra": "forbid"}


class RegistrationResponse(BaseModel):
    id: str
    status: str
    course_title: str
    registration_type: str
    first_name: str
    last_name: str
    email: str
    currency: Optional[str] = "USD"

    model_config = {"from_attributes": True}
