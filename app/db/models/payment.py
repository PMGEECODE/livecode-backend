import uuid
from sqlalchemy import Column, String, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base_class import Base


class PaymentTransaction(Base):
    __tablename__ = "payment_transaction"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registration_id = Column(UUID(as_uuid=True), ForeignKey("course_registration.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Mpesa STK variables
    checkout_request_id = Column(String, nullable=False, unique=True, index=True)
    merchant_request_id = Column(String, nullable=True)
    
    amount = Column(Float, nullable=False)
    phone_number = Column(String, nullable=False)
    
    # Status: pending | completed | failed
    status = Column(String, nullable=False, default="pending")
    
    # Safaricom specific callback details
    mpesa_receipt_number = Column(String, nullable=True)
    result_code = Column(String, nullable=True)
    result_desc = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __init__(
        self,
        *,
        registration_id,
        checkout_request_id,
        merchant_request_id=None,
        amount,
        phone_number,
        status="pending",
        mpesa_receipt_number=None,
        result_code=None,
        result_desc=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.registration_id = registration_id
        self.checkout_request_id = checkout_request_id
        self.merchant_request_id = merchant_request_id
        self.amount = amount
        self.phone_number = phone_number
        self.status = status
        self.mpesa_receipt_number = mpesa_receipt_number
        self.result_code = result_code
        self.result_desc = result_desc
