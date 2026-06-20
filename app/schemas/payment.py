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
    payment_token: Optional[str] = None


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


class PaypalCreateOrderRequest(BaseModel):
    registration_id: UUID

    model_config = {
        "extra": "forbid"
    }


class PaypalCaptureRequest(BaseModel):
    registration_id: UUID
    order_id: str

    model_config = {
        "extra": "forbid"
    }


class PaypalConfigResponse(BaseModel):
    client_id: str
    mode: str


class PaystackInitializeRequest(BaseModel):
    registration_id: UUID

    model_config = {
        "extra": "forbid"
    }


class PaystackInitializeResponse(BaseModel):
    authorization_url: str
    access_code: str
    reference: str
    amount: float
    currency: str
    status: str = "pending"


class PaystackStatusResponse(BaseModel):
    registration_id: UUID
    reference: str
    status: str
    amount: float
    currency: str
    receipt_number: Optional[str] = None
    message: Optional[str] = None


class PaymentOptionResponse(BaseModel):
    provider: str
    label: str
    is_enabled: bool
    disabled_message: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class PaymentOptionUpdate(BaseModel):
    is_enabled: bool
    disabled_message: Optional[str] = Field(None, max_length=500)

    model_config = {
        "extra": "forbid"
    }


class PaymentOptionsResponse(BaseModel):
    options: list[PaymentOptionResponse]
