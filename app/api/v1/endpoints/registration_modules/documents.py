import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.core.document_generators import (
    generate_invoice_pdf,
    generate_invitation_letter_pdf,
    generate_pre_training_form_docx,
)
from app.db.models.course import Course
from app.db.models.payment import PaymentTransaction
from app.db.models.registration import CourseRegistration

router = APIRouter()


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "document").strip("._")
    return cleaned[:120] or "document"


def _download_headers(filename: str) -> dict[str, str]:
    safe_filename = _safe_filename(filename)
    return {
        "Content-Disposition": f'attachment; filename="{safe_filename}"',
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }


@router.get(
    "/{id}/invoice",
    summary="Download dynamically generated registration invoice PDF",
)
async def download_invoice(
    id: uuid.UUID,
    currency: str = None,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Generate and stream a professional 3-page Invoice PDF for a course registration.
    """
    if currency and currency.upper() not in {"USD", "KES"}:
        raise HTTPException(status_code=400, detail="Unsupported invoice currency")

    result = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == id))
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
        
    course = None
    if registration.course_id:
        course_res = await db.execute(
            select(Course)
            .options(selectinload(Course.logistics))
            .filter(Course.id == registration.course_id)
        )
        course = course_res.scalars().first()

    payment_result = await db.execute(
        select(PaymentTransaction)
        .filter(PaymentTransaction.registration_id == registration.id)
        .order_by(PaymentTransaction.created_at.desc())
    )
    latest_payment = payment_result.scalars().first()
    if latest_payment:
        payment_provider = (latest_payment.provider or "").lower()
        if latest_payment.checkout_request_id.startswith("paypal_"):
            payment_provider = "paypal"
        elif latest_payment.checkout_request_id.startswith("stripe_"):
            payment_provider = "stripe"
        elif latest_payment.checkout_request_id.startswith("psk_"):
            payment_provider = "paystack"

        provider_labels = {
            "paypal": "PayPal (Online)",
            "paystack": "Paystack Card (Online)",
            "mpesa": "M-Pesa (Online)",
            "stripe": "Stripe (Online)",
        }
        payment_method = provider_labels.get(
            payment_provider,
            latest_payment.provider or "Online Payment",
        )
        if latest_payment.status == "completed":
            registration.status = "confirmed"
        setattr(registration, "payment_method", payment_method)
        
    # Default to the registered currency if not explicitly overridden via query param
    inv_currency = currency if currency else (registration.currency or "USD")
    pdf_buffer = generate_invoice_pdf(registration, course, currency=inv_currency)
    filename = f"Invoice_{registration.first_name}_{registration.last_name}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers=_download_headers(filename),
    )


@router.get(
    "/{id}/invitation-letter",
    summary="Download dynamically generated registration invitation letter PDF",
)
async def download_invitation_letter(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Generate and stream a professional 6-page Invitation Letter PDF with syllabus for a course registration.
    """
    result = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == id))
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
        
    course = None
    if registration.course_id:
        course_res = await db.execute(
            select(Course)
            .options(selectinload(Course.logistics))
            .filter(Course.id == registration.course_id)
        )
        course = course_res.scalars().first()
        
    pdf_buffer = generate_invitation_letter_pdf(registration, course)
    filename = f"Invitation_Letter_{registration.first_name}_{registration.last_name}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers=_download_headers(filename),
    )


@router.get(
    "/{id}/pre-training-form",
    summary="Download dynamically generated pre-training evaluation form DOCX",
)
async def download_pre_training_form(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Generate and stream a professional Word DOCX Pre-Training assessment form for a course registration.
    """
    result = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == id))
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
        
    course = None
    if registration.course_id:
        course_res = await db.execute(
            select(Course)
            .options(selectinload(Course.logistics))
            .filter(Course.id == registration.course_id)
        )
        course = course_res.scalars().first()
        
    docx_buffer = generate_pre_training_form_docx(registration, course)
    filename = f"Pre_Training_Form_{registration.first_name}_{registration.last_name}.docx"
    
    return StreamingResponse(
        docx_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_download_headers(filename),
    )
