from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class MpesaStkPushRequest(BaseModel):
    registration_id: UUID
    phone_number: str = Field(..., description="Phone number in the format 2547XXXXXXXX or 07XXXXXXXX")
    amount: float = Field(..., gt=0, description="Amount to be paid")

    model_config = {
        "extra": "forbid"
    }


class MpesaStkPushResponse(BaseModel):
    checkout_request_id: str
    merchant_request_id: str
    customer_message: str


class MpesaStatusResponse(BaseModel):
    status: str  # pending | completed | failed
    checkout_request_id: str
    amount: float
    phone_number: str
    mpesa_receipt_number: Optional[str] = None
    result_desc: Optional[str] = None


class StripeChargeRequest(BaseModel):
    registration_id: UUID
    number: str = Field(..., description="Card number")
    exp_month: str = Field(..., description="Expiry month")
    exp_year: str = Field(..., description="Expiry year")
    cvc: str = Field(..., description="CVC")
    amount: float = Field(..., gt=0, description="Amount to be paid")
    currency: str = Field(..., description="Currency (USD or KES)")

    model_config = {
        "extra": "forbid"
    }
