import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.api.v1.endpoints.registration import process_registration_email
from app.core.config import settings
from app.core.limiter import limiter
from app.db.models.course import Course
from app.db.models.payment import PaymentTransaction
from app.db.models.registration import CourseRegistration
from app.schemas.payment import PaystackInitializeRequest, PaystackInitializeResponse, PaystackStatusResponse
from app.services.paystack import paystack_service
from app.services.payment_options import ensure_payment_provider_enabled
from app.api.v1.endpoints.payment_modules.shared import (
    build_course_email_payload,
    build_registration_email_payload,
    calculate_registration_payment,
    get_registration_course_for_payment,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def finalize_paystack_payment(
    *,
    reference: str,
    verification_data: dict[str, Any],
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> PaymentTransaction:
    tx_stmt = select(PaymentTransaction).filter(
        PaymentTransaction.provider == "paystack",
        PaymentTransaction.checkout_request_id == reference,
    )
    tx_result = await db.execute(tx_stmt)
    transaction = tx_result.scalars().first()
    if not transaction:
        logger.warning("Paystack verification for unknown reference: %s", reference)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment transaction not found.")

    if transaction.status == "completed":
        return transaction

    reg_stmt = select(CourseRegistration).filter(CourseRegistration.id == transaction.registration_id)
    reg_result = await db.execute(reg_stmt)
    registration = reg_result.scalars().first()
    if not registration:
        transaction.status = "failed"
        transaction.result_desc = "Registration not found during Paystack verification"
        db.add(transaction)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registration record not found.")

    course_stmt = (
        select(Course)
        .options(selectinload(Course.logistics), selectinload(Course.schedules))
        .filter(Course.id == registration.course_id)
    )
    course_result = await db.execute(course_stmt)
    course = course_result.scalars().first()
    if not course:
        transaction.status = "failed"
        transaction.result_desc = "Course not found during Paystack verification"
        db.add(transaction)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated course not found.")

    expected_amount, expected_currency = calculate_registration_payment(registration, course)
    expected_subunit = int(round(expected_amount * 100))
    paid_subunit = int(verification_data.get("amount") or 0)
    paid_currency = str(verification_data.get("currency") or "").upper()
    paystack_status = str(verification_data.get("status") or "").lower()

    transaction.gateway_response = json.dumps(verification_data, default=str)
    transaction.provider_reference = reference
    transaction.currency = expected_currency

    if (
        paystack_status != "success"
        or paid_subunit != expected_subunit
        or paid_currency != expected_currency
    ):
        transaction.status = "failed"
        transaction.result_code = paystack_status or "verification_failed"
        transaction.result_desc = (
            "Paystack verification failed: amount, currency, or status did not match."
        )
        db.add(transaction)
        await db.commit()
        logger.warning(
            "Paystack verification mismatch reference=%s expected=%s %s paid=%s %s status=%s",
            reference,
            expected_subunit,
            expected_currency,
            paid_subunit,
            paid_currency,
            paystack_status,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment verification failed.")

    transaction.status = "completed"
    transaction.amount = expected_amount
    transaction.mpesa_receipt_number = str(verification_data.get("id") or verification_data.get("reference") or reference)
    transaction.result_code = "0"
    transaction.result_desc = "Paystack payment verified successfully"
    paid_at_raw = verification_data.get("paid_at") or verification_data.get("paidAt")
    if paid_at_raw:
        try:
            transaction.paid_at = datetime.fromisoformat(str(paid_at_raw).replace("Z", "+00:00"))
        except ValueError:
            transaction.paid_at = datetime.now(timezone.utc)
    else:
        transaction.paid_at = datetime.now(timezone.utc)

    should_send_email = registration.status != "confirmed"
    reg_email_payload = build_registration_email_payload(registration, "Paystack Card (Online)")
    course_email_payload = build_course_email_payload(course)
    registration.status = "confirmed"
    registration.currency = expected_currency
    db.add(registration)
    db.add(transaction)

    await db.commit()
    await db.refresh(transaction)

    if should_send_email:
        background_tasks.add_task(
            process_registration_email,
            reg_email_payload,
            course_email_payload,
        )

    return transaction


@router.post(
    "/paystack/initialize",
    response_model=PaystackInitializeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize Paystack hosted card payment",
)
@limiter.limit("5/minute")
async def paystack_initialize(
    request: Request,
    response: Response,
    payload: PaystackInitializeRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    await ensure_payment_provider_enabled(db, "paystack")
    registration, course = await get_registration_course_for_payment(db, payload.registration_id)

    if registration.status == "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This registration has already been paid and confirmed.",
        )

    amount, currency = calculate_registration_payment(registration, course)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount could not be calculated for this registration.",
        )

    now_utc = datetime.now(timezone.utc)
    existing_stmt = select(PaymentTransaction).filter(
        PaymentTransaction.registration_id == registration.id,
        PaymentTransaction.provider == "paystack",
        PaymentTransaction.status == "pending",
    )
    existing_result = await db.execute(existing_stmt)
    for existing in existing_result.scalars().all():
        created_at = existing.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if (
            created_at
            and now_utc - created_at < timedelta(minutes=15)
            and existing.authorization_url
            and existing.access_code
        ):
            return PaystackInitializeResponse(
                authorization_url=existing.authorization_url,
                access_code=existing.access_code,
                reference=existing.checkout_request_id,
                amount=existing.amount,
                currency=existing.currency or currency,
            )

    callback_url = settings.PAYSTACK_CALLBACK_URL or f"{settings.PUBLIC_SITE_URL.rstrip('/')}/api/v1/payments/paystack/callback"
    reference = f"psk_{str(registration.id).replace('-', '')[:18]}_{uuid.uuid4().hex[:12]}"
    metadata = {
        "registration_id": str(registration.id),
        "course_id": str(registration.course_id) if registration.course_id else None,
        "course_title": registration.course_title,
        "customer_name": f"{registration.first_name} {registration.last_name}".strip(),
        "expected_amount": amount,
        "expected_currency": currency,
    }

    initialized = await paystack_service.initialize_transaction(
        email=registration.email,
        amount=amount,
        currency=currency,
        reference=reference,
        callback_url=callback_url,
        metadata=metadata,
    )

    transaction = PaymentTransaction(
        registration_id=registration.id,
        checkout_request_id=reference,
        merchant_request_id=initialized.get("access_code"),
        amount=amount,
        phone_number=registration.phone or "Paystack",
        status="pending",
        provider="paystack",
        provider_reference=reference,
        currency=currency,
        authorization_url=initialized["authorization_url"],
        access_code=initialized.get("access_code"),
        metadata_json=json.dumps(metadata),
    )
    db.add(transaction)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Error saving Paystack transaction: %s", repr(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save Paystack payment transaction.",
        )

    return PaystackInitializeResponse(
        authorization_url=initialized["authorization_url"],
        access_code=initialized.get("access_code") or "",
        reference=reference,
        amount=amount,
        currency=currency,
    )


@router.get(
    "/paystack/status/{reference}",
    response_model=PaystackStatusResponse,
    summary="Get Paystack payment status",
)
async def paystack_status(
    reference: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = select(PaymentTransaction).filter(
        PaymentTransaction.provider == "paystack",
        PaymentTransaction.checkout_request_id == reference,
    )
    result = await db.execute(stmt)
    transaction = result.scalars().first()
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment transaction not found.")

    if transaction.status == "pending":
        try:
            verification = await paystack_service.verify_transaction(reference)
            transaction = await finalize_paystack_payment(
                reference=reference,
                verification_data=verification,
                background_tasks=background_tasks,
                db=db,
            )
        except HTTPException as exc:
            if exc.status_code not in {status.HTTP_400_BAD_REQUEST, status.HTTP_502_BAD_GATEWAY}:
                raise

    return PaystackStatusResponse(
        registration_id=transaction.registration_id,
        reference=transaction.checkout_request_id,
        status=transaction.status,
        amount=transaction.amount,
        currency=transaction.currency or "USD",
        receipt_number=transaction.mpesa_receipt_number,
        message=transaction.result_desc,
    )


@router.get(
    "/paystack/callback",
    summary="Paystack browser callback",
)
async def paystack_callback(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    reference: str | None = None,
    trxref: str | None = None,
) -> Any:
    payment_reference = reference or trxref
    frontend_base = settings.paystack_frontend_return_url

    if not payment_reference:
        return RedirectResponse(
            url=f"{frontend_base}/payment/paystack/complete?status=failed&reason=missing_reference",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    async def build_paystack_return_url(
        *,
        transaction: PaymentTransaction | None,
        redirect_status: str,
    ) -> str:
        registration_id = str(transaction.registration_id) if transaction else ""
        if transaction:
            registration_result = await db.execute(
                select(CourseRegistration).filter(CourseRegistration.id == transaction.registration_id)
            )
            registration = registration_result.scalars().first()
            if registration and registration.course_id:
                course_result = await db.execute(
                    select(Course).filter(Course.id == registration.course_id)
                )
                course = course_result.scalars().first()
                if course and course.slug:
                    return (
                        f"{frontend_base}/trainings/{course.slug}/register"
                        f"?payment_provider=paystack&payment_status={redirect_status}"
                        f"&reference={payment_reference}&registration_id={registration_id}"
                    )

        return (
            f"{frontend_base}/payment/paystack/complete"
            f"?status={redirect_status}&reference={payment_reference}&registration_id={registration_id}"
        )

    redirect_registration_id = ""
    redirect_status = "failed"
    transaction = None
    try:
        verification = await paystack_service.verify_transaction(payment_reference)
        transaction = await finalize_paystack_payment(
            reference=payment_reference,
            verification_data=verification,
            background_tasks=background_tasks,
            db=db,
        )
        redirect_registration_id = str(transaction.registration_id)
        redirect_status = "success" if transaction.status == "completed" else transaction.status
    except Exception as exc:
        logger.warning("Paystack callback verification failed for %s: %s", payment_reference, repr(exc))
        stmt = select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == payment_reference)
        result = await db.execute(stmt)
        transaction = result.scalars().first()
        if transaction:
            redirect_registration_id = str(transaction.registration_id)

    return RedirectResponse(
        url=(
            await build_paystack_return_url(
                transaction=transaction,
                redirect_status=redirect_status,
            )
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/paystack/webhook",
    summary="Paystack webhook event synchronization",
)
async def paystack_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Any:
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not paystack_service.verify_webhook_signature(raw_body, signature):
        logger.warning("Paystack webhook signature verification failed.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Signature verification failed.")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    event = payload.get("event")
    data = payload.get("data") or {}
    reference = data.get("reference")
    logger.info("Paystack webhook received: %s", event)

    if event == "charge.success" and reference:
        try:
            await finalize_paystack_payment(
                reference=reference,
                verification_data=data,
                background_tasks=background_tasks,
                db=db,
            )
        except HTTPException as exc:
            logger.warning("Paystack webhook processing skipped for %s: %s", reference, exc.detail)

    return Response(status_code=status.HTTP_200_OK)
