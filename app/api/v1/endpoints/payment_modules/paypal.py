import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.api.v1.endpoints.registration import process_registration_email
from app.core.config import settings
from app.db.models.course import Course
from app.db.models.payment import PaymentTransaction
from app.db.models.registration import CourseRegistration
from app.schemas.payment import PaypalCaptureRequest, PaypalConfigResponse, PaypalCreateOrderRequest
from app.services.paypal import paypal_service
from app.api.v1.endpoints.payment_modules.shared import calculate_registration_total

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get(
    "/paypal/config",
    response_model=PaypalConfigResponse,
    summary="Get PayPal client configuration",
)
async def get_paypal_config() -> Any:
    """
    Returns PayPal Client ID and Mode for frontend SDK setup.
    """
    if not settings.PAYPAL_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PayPal Client ID is not configured on the server.",
        )
    return PaypalConfigResponse(
        client_id=settings.PAYPAL_CLIENT_ID,
        mode=settings.PAYPAL_MODE or "sandbox",
    )


@router.post(
    "/paypal/create-order",
    summary="Create PayPal payment order",
)
async def paypal_create_order(
    payload: PaypalCreateOrderRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Creates a PayPal order on behalf of the client.
    Verifies amount dynamically using backend database.
    """
    # 1. Fetch course registration
    stmt = select(CourseRegistration).filter(CourseRegistration.id == payload.registration_id)
    result = await db.execute(stmt)
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration record not found.",
        )

    if registration.status == "confirmed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This registration has already been paid and confirmed.",
        )

    # 2. Fetch course with logistics and schedules
    course_stmt = (
        select(Course)
        .options(selectinload(Course.logistics), selectinload(Course.schedules))
        .filter(Course.id == registration.course_id)
    )
    course_result = await db.execute(course_stmt)
    course = course_result.scalars().first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated course not found.",
        )

    # 3. Calculate expected USD price
    amount_usd = calculate_registration_total(registration, course)

    # 4. Request order creation via PayPal Service
    description = f"Course Registration: {registration.course_title} ({registration.id})"
    try:
        paypal_order = await paypal_service.create_order(
            registration_id=str(registration.id),
            amount_usd=amount_usd,
            description=description,
        )
    except Exception as e:
        logger.error(f"Error creating PayPal order: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to initiate transaction with PayPal.",
        )

    order_id = paypal_order.get("id")
    if not order_id:
        logger.error(f"Invalid PayPal response: {paypal_order}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve Order ID from PayPal.",
        )

    # 5. Save pending transaction record
    # For KES payments, save original KES value in transaction to match receipt expectations
    actual_amount = amount_usd
    if registration.currency == "KES":
        # Recalculate full KES amount to save in DB
        participant_count = 1
        if registration.registration_type == "group" and registration.group_size:
            try:
                participant_count = int(registration.group_size)
            except ValueError:
                pass
        
        # Calculate unit price in KES
        matched_schedule = None
        if course.schedules:
            for s in course.schedules:
                if s.date_range == registration.schedule_date and s.location == registration.schedule_location:
                    matched_schedule = s
                    break
        unit_price = None
        if matched_schedule and matched_schedule.price_kes:
            unit_price = matched_schedule.price_kes
        elif course.logistics and course.logistics.price_kes:
            unit_price = course.logistics.price_kes
        
        if unit_price is None:
            usd_price = None
            if matched_schedule and matched_schedule.price_usd:
                usd_price = matched_schedule.price_usd
            elif course.logistics and course.logistics.price_usd:
                usd_price = course.logistics.price_usd
            unit_price = (usd_price or 1500.0) * 130.0
            
        subtotal = unit_price * participant_count
        actual_amount = subtotal + (subtotal * 0.16)

    transaction = PaymentTransaction(
        registration_id=registration.id,
        checkout_request_id=f"paypal_{order_id}",
        merchant_request_id=f"paypal_order_{order_id}",
        amount=actual_amount,
        phone_number=registration.phone or "PayPal",
        status="pending",
        provider="paypal",
        provider_reference=order_id,
        currency=registration.currency or "USD",
    )
    db.add(transaction)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Error saving PayPal transaction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save payment transaction.",
        )

    return {"order_id": order_id}


@router.post(
    "/paypal/capture-order",
    summary="Capture PayPal payment order",
)
async def paypal_capture_order(
    payload: PaypalCaptureRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Captures a PayPal order payment and confirms the corresponding registration.
    """
    # 1. Fetch course registration
    stmt = select(CourseRegistration).filter(CourseRegistration.id == payload.registration_id)
    result = await db.execute(stmt)
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration record not found.",
        )

    # Idempotency check: if registration is already confirmed, return success without double processing
    if registration.status == "confirmed":
        return {
            "status": "success",
            "message": "Payment processed and registration confirmed.",
        }

    # 2. Fetch or create transaction
    tx_stmt = select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == f"paypal_{payload.order_id}")
    tx_result = await db.execute(tx_stmt)
    transaction = tx_result.scalars().first()

    # 3. Capture payment on PayPal
    try:
        capture_res = await paypal_service.capture_order(payload.order_id)
    except Exception as e:
        logger.error(f"Error capturing PayPal payment: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="PayPal order capture failed.",
        )

    # 4. Check capture status
    purchase_units = capture_res.get("purchase_units", [])
    captured = False
    capture_id = None
    for unit in purchase_units:
        payments = unit.get("payments", {})
        captures = payments.get("captures", [])
        for capture in captures:
            if capture.get("status") == "COMPLETED":
                captured = True
                capture_id = capture.get("id")
                break

    if not captured:
        logger.error(f"PayPal Order {payload.order_id} was not fully captured: {capture_res}")
        if transaction:
            transaction.status = "failed"
            transaction.result_desc = "PayPal capture not completed"
            db.add(transaction)
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PayPal payment was not authorized or captured.",
        )

    # 5. Inside atomic transaction, confirm registration and update transaction
    registration.status = "confirmed"
    db.add(registration)

    if not transaction:
        # Fallback if create-order failed to save transaction record
        # Determine course base price to log the correct amount
        course_stmt = (
            select(Course)
            .options(selectinload(Course.logistics), selectinload(Course.schedules))
            .filter(Course.id == registration.course_id)
        )
        course_res = await db.execute(course_stmt)
        course = course_res.scalars().first()
        amount_usd = calculate_registration_total(registration, course) if course else 1500.0
        
        transaction = PaymentTransaction(
            registration_id=registration.id,
            checkout_request_id=f"paypal_{payload.order_id}",
            merchant_request_id=f"paypal_order_{payload.order_id}",
            amount=amount_usd,
            phone_number=registration.phone or "PayPal",
            status="pending",
            provider="paypal",
            provider_reference=payload.order_id,
            currency=registration.currency or "USD",
        )

    transaction.status = "completed"
    transaction.mpesa_receipt_number = capture_id or payload.order_id  # Save PayPal transaction ID as receipt number
    transaction.result_code = "0"
    transaction.result_desc = "PayPal capture successful"
    db.add(transaction)

    # Extract info for background email
    reg_id = registration.id
    course_id = registration.course_id
    course_title = registration.course_title
    schedule_date = registration.schedule_date
    schedule_location = registration.schedule_location
    registration_type = registration.registration_type
    reg_title = registration.title
    first_name = registration.first_name
    last_name = registration.last_name
    organization = registration.organization
    country = registration.country
    email = registration.email
    phone = registration.phone
    department = registration.department
    group_size = registration.group_size
    group_members_json = registration.group_members_json
    reg_currency = registration.currency

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Error finalizing PayPal capture updates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error updating payment records.",
        )

    # 6. Trigger confirmation email
    from app.crud.course import course as crud_course
    course_dict = None
    if course_id:
        course = await crud_course.get(db=db, id=course_id)
        if course:
            course_dict = {
                "id": str(course.id),
                "title": course.title,
            }
            if course.logistics:
                course_dict["logistics"] = {
                    "location": course.logistics.location,
                    "start_date": course.logistics.start_date.isoformat() if hasattr(course.logistics.start_date, 'isoformat') else course.logistics.start_date,
                    "end_date": course.logistics.end_date.isoformat() if hasattr(course.logistics.end_date, 'isoformat') else course.logistics.end_date,
                    "duration": course.logistics.duration,
                    "price_usd": float(course.logistics.price_usd) if course.logistics.price_usd else 0.0,
                }

    reg_dict = {
        "id": reg_id,
        "course_id": str(course_id) if course_id else None,
        "course_title": course_title,
        "schedule_date": schedule_date,
        "schedule_location": schedule_location,
        "registration_type": registration_type,
        "title": reg_title,
        "first_name": first_name,
        "last_name": last_name,
        "organization": organization,
        "country": country,
        "email": email,
        "phone": phone,
        "department": department,
        "group_size": group_size,
        "group_members_json": group_members_json,
        "currency": reg_currency,
        "payment_method": "PayPal (Online)",
        "status": "confirmed",
    }
    background_tasks.add_task(process_registration_email, reg_dict, course_dict)

    return {
        "status": "success",
        "message": "PayPal payment captured successfully.",
    }


@router.post(
    "/paypal/webhook",
    summary="PayPal Webhook event synchronization",
)
async def paypal_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Webhook handler for PayPal payment notifications.
    Keeps database in sync in case client-side flow fails.
    Verifies PayPal signature securely to prevent spoofing.
    """
    webhook_id = settings.PAYPAL_WEBHOOK_ID
    if not webhook_id:
        logger.warning("PayPal Webhook ID is not configured. Webhook cannot verify signatures securely.")
        return Response(status_code=status.HTTP_200_OK)

    # 1. Read headers and raw body
    headers = dict(request.headers)
    body = await request.body()

    # 2. Verify signature securely
    verified = await paypal_service.verify_webhook_signature(headers, body, webhook_id)
    if not verified:
        logger.warning("PayPal Webhook signature verification failed.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signature verification failed.",
        )

    # 3. Process webhook event
    import json
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    event_type = payload.get("event_type")
    resource = payload.get("resource", {})

    logger.info(f"PayPal webhook event received: {event_type}")

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        # Extract Order ID and Capture ID
        links = resource.get("links", [])
        order_id = None
        for link in links:
            if link.get("rel") == "up":
                # The href usually ends with /v2/checkout/orders/{order_id}
                href = link.get("href", "")
                parts = href.split("/")
                if len(parts) > 0:
                    order_id = parts[-1]
                break
        
        if not order_id:
            # Fallback check for alternate properties
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")

        if not order_id:
            logger.warning(f"Could not extract Order ID from capture payload: {resource}")
            return Response(status_code=status.HTTP_200_OK)

        capture_id = resource.get("id")

        # Fetch transaction
        tx_stmt = select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == f"paypal_{order_id}")
        tx_result = await db.execute(tx_stmt)
        transaction = tx_result.scalars().first()

        if transaction:
            if transaction.status == "completed":
                # Already processed
                return Response(status_code=status.HTTP_200_OK)

            # Inside atomic transaction, confirm registration
            reg_stmt = select(CourseRegistration).filter(CourseRegistration.id == transaction.registration_id)
            reg_res = await db.execute(reg_stmt)
            registration = reg_res.scalars().first()

            if registration:
                registration.status = "confirmed"
                db.add(registration)

                transaction.status = "completed"
                transaction.mpesa_receipt_number = capture_id or order_id
                transaction.result_code = "0"
                transaction.result_desc = "PayPal capture completed (via webhook)"
                db.add(transaction)

                # Fetch course details for registration email
                course_stmt = (
                    select(Course)
                    .options(selectinload(Course.logistics))
                    .filter(Course.id == registration.course_id)
                )
                course_res = await db.execute(course_stmt)
                course = course_res.scalars().first()

                course_dict = None
                if course:
                    course_dict = {
                        "id": str(course.id),
                        "title": course.title,
                    }
                    if course.logistics:
                        course_dict["logistics"] = {
                            "location": course.logistics.location,
                            "start_date": course.logistics.start_date.isoformat() if hasattr(course.logistics.start_date, 'isoformat') else course.logistics.start_date,
                            "end_date": course.logistics.end_date.isoformat() if hasattr(course.logistics.end_date, 'isoformat') else course.logistics.end_date,
                            "duration": course.logistics.duration,
                            "price_usd": float(course.logistics.price_usd) if course.logistics.price_usd else 0.0,
                        }

                reg_dict = {
                    "id": registration.id,
                    "course_id": str(registration.course_id) if registration.course_id else None,
                    "course_title": registration.course_title,
                    "schedule_date": registration.schedule_date,
                    "schedule_location": registration.schedule_location,
                    "registration_type": registration.registration_type,
                    "title": registration.title,
                    "first_name": registration.first_name,
                    "last_name": registration.last_name,
                    "organization": registration.organization,
                    "country": registration.country,
                    "email": registration.email,
                    "phone": registration.phone,
                    "department": registration.department,
                    "group_size": registration.group_size,
                    "group_members_json": registration.group_members_json,
                    "currency": registration.currency,
                    "payment_method": "PayPal (Online)",
                    "status": "confirmed",
                }
                
                background_tasks.add_task(process_registration_email, reg_dict, course_dict)
                await db.commit()
                logger.info(f"Successfully processed webhook capture registration for {reg_dict['email']}")

    return Response(status_code=status.HTTP_200_OK)
