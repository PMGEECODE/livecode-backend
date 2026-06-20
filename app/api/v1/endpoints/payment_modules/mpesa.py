import logging
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from jose import jwt

from app.api.deps import get_db
from app.api.v1.endpoints.registration import process_registration_email
from app.core.limiter import limiter
from app.core.redis import redis_manager
from app.core.config import settings
from app.core.metrics import metrics_registry
from app.db.session import SessionLocal
from app.db.models.course import Course
from app.db.models.payment import PaymentTransaction
from app.db.models.registration import CourseRegistration
from app.schemas.payment import MpesaStkPushRequest, MpesaStkPushResponse, MpesaStatusResponse
from app.services.mpesa import mpesa_service
from app.services.payment_options import ensure_payment_provider_enabled

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/mpesa/stk-push",
    response_model=MpesaStkPushResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate Mpesa STK Push",
)
@limiter.limit("5/minute")
async def initiate_stk_push(
    request: Request,
    response: Response,
    payload: MpesaStkPushRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Initiate Mpesa STK Push for course registration payment.
    - Verifies that the registration exists.
    - Requests the STK Push via Safaricom API.
    - Saves the pending transaction.
    """
    await ensure_payment_provider_enabled(db, "mpesa")

    # 1. Fetch course registration
    stmt = select(CourseRegistration).filter(CourseRegistration.id == payload.registration_id)
    result = await db.execute(stmt)
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration record not found.",
        )

    # Idempotency check: if registration is already confirmed
    if registration.status == "confirmed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This registration has already been paid and confirmed.",
        )

    # Check for existing pending transaction within the last 30 seconds to prevent duplicate pushes
    from datetime import datetime, timedelta, timezone
    now_utc = datetime.now(timezone.utc)
    tx_stmt = select(PaymentTransaction).filter(
        PaymentTransaction.registration_id == payload.registration_id,
        PaymentTransaction.status == "pending"
    )
    tx_result = await db.execute(tx_stmt)
    existing_txs = tx_result.scalars().all()
    for tx in existing_txs:
        tx_created = tx.created_at
        if tx_created:
            if tx_created.tzinfo is None:
                tx_created = tx_created.replace(tzinfo=timezone.utc)
            if now_utc - tx_created < timedelta(seconds=30):
                token_data = {
                    "sub": tx.checkout_request_id,
                    "registration_id": str(payload.registration_id),
                    "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
                }
                payment_token = jwt.encode(
                    token_data,
                    settings.SECRET_KEY,
                    algorithm=settings.JWT_ALGORITHM
                )
                return MpesaStkPushResponse(
                    checkout_request_id=tx.checkout_request_id,
                    merchant_request_id=tx.merchant_request_id or "",
                    customer_message="Payment request is already processing. Please approve the prompt on your phone.",
                    payment_token=payment_token,
                )

    # 2. Trigger Safaricom STK Push
    try:
        response_data = await mpesa_service.initiate_stk_push(
            phone_number=payload.phone_number,
            amount=payload.amount,
            account_reference=registration.course_title,
        )
    except Exception as e:
        logger.error(f"STK Push error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "M-Pesa STK Push request failed.",
        )

    # 3. Parse STK response
    checkout_request_id = response_data.get("CheckoutRequestID")
    merchant_request_id = response_data.get("MerchantRequestID")
    customer_message = response_data.get("CustomerMessage", "STK push initiated successfully.")

    if not checkout_request_id:
        logger.error(f"Safaricom response did not return CheckoutRequestID: {response_data}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response from Safaricom.",
        )

    # 4. Save pending transaction
    transaction = PaymentTransaction(
        registration_id=payload.registration_id,
        checkout_request_id=checkout_request_id,
        merchant_request_id=merchant_request_id,
        amount=payload.amount,
        phone_number=payload.phone_number,
        status="pending",
    )
    db.add(transaction)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error saving payment transaction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save payment transaction.",
        )

    token_data = {
        "sub": checkout_request_id,
        "registration_id": str(payload.registration_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    payment_token = jwt.encode(
        token_data,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    metrics_registry.increment_counter("mpesa_stk_requests_total")

    return MpesaStkPushResponse(
        checkout_request_id=checkout_request_id,
        merchant_request_id=merchant_request_id or "",
        customer_message=customer_message,
        payment_token=payment_token,
    )


@router.get(
    "/mpesa/status/{checkout_request_id}",
    response_model=MpesaStatusResponse,
    summary="Get Mpesa STK status",
)
async def get_mpesa_status(
    checkout_request_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Get the status of an Mpesa STK Push transaction.
    """
    stmt = select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == checkout_request_id)
    result = await db.execute(stmt)
    transaction = result.scalars().first()
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found.",
        )

    return MpesaStatusResponse(
        status=transaction.status,
        checkout_request_id=transaction.checkout_request_id,
        amount=transaction.amount,
        phone_number=transaction.phone_number,
        mpesa_receipt_number=transaction.mpesa_receipt_number,
        result_desc=transaction.result_desc,
    )


@router.post(
    "/mpesa/callback",
    summary="Callback URL for Lipa Na Mpesa STK push",
)
async def mpesa_callback(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Callback webhook for Safaricom to report payment status.
    Updates the database transaction status and registration status.
    Triggers registration confirmation email in case of success.
    """
    logger.info(f"Mpesa callback received: {payload}")
    
    stk_callback = payload.get("Body", {}).get("stkCallback", {})
    checkout_request_id = stk_callback.get("CheckoutRequestID")
    result_code = stk_callback.get("ResultCode")
    result_desc = stk_callback.get("ResultDesc")

    if not checkout_request_id:
        logger.warning("Callback received without CheckoutRequestID")
        return {"ResultCode": 1, "ResultDesc": "Invalid payload"}

    # 1. Fetch transaction
    stmt = select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == checkout_request_id)
    res = await db.execute(stmt)
    transaction = res.scalars().first()
    if not transaction:
        logger.warning(f"Transaction with CheckoutRequestID {checkout_request_id} not found in DB")
        return {"ResultCode": 1, "ResultDesc": "Transaction not found"}

    if transaction.status != "pending":
        logger.info(f"Transaction {checkout_request_id} already processed with status: {transaction.status}")
        return {"ResultCode": 0, "ResultDesc": "Already processed"}

    # 2. Parse callback metadata on success (ResultCode == 0)
    receipt_number = None
    if result_code == 0:
        callback_metadata = stk_callback.get("CallbackMetadata", {}).get("Item", [])
        for item in callback_metadata:
            if item.get("Name") == "MpesaReceiptNumber":
                receipt_number = item.get("Value")
                break
        
        transaction.status = "completed"
        transaction.mpesa_receipt_number = receipt_number
        transaction.result_code = str(result_code)
        transaction.result_desc = result_desc

        # 3. Update registration status to confirmed
        reg_stmt = select(CourseRegistration).filter(CourseRegistration.id == transaction.registration_id)
        reg_res = await db.execute(reg_stmt)
        registration = reg_res.scalars().first()
        if registration:
            if registration.status == "pending":
                registration.status = "confirmed"
                registration.currency = "KES"  # Always KES for M-Pesa
                db.add(registration)
                
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
                            "price_kes": float(course.logistics.price_kes) if hasattr(course.logistics, "price_kes") and course.logistics.price_kes else 0.0,
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
                    "currency": "KES",
                    "payment_method": "M-Pesa (Online)",
                    "status": "confirmed",
                }
                
                background_tasks.add_task(process_registration_email, reg_dict, course_dict)
                logger.info(f"Successfully processed registration email for {registration.email}")

    else:
        # Failed transaction
        transaction.status = "failed"
        transaction.result_code = str(result_code)
        transaction.result_desc = result_desc

    tx_status = transaction.status
    tx_checkout_id = transaction.checkout_request_id
    tx_amount = transaction.amount
    tx_phone = transaction.phone_number
    tx_receipt = transaction.mpesa_receipt_number
    tx_desc = transaction.result_desc

    db.add(transaction)
    try:
        await db.commit()
        await redis_manager.delete_pattern("dashboard:*")
        await redis_manager.delete_pattern("registrations:*")
        
        # Publish update to Redis Pub/Sub
        if redis_manager.client:
            try:
                event_payload = {
                    "status": tx_status,
                    "checkout_request_id": tx_checkout_id,
                    "amount": tx_amount,
                    "phone_number": tx_phone,
                    "mpesa_receipt_number": tx_receipt,
                    "result_desc": tx_desc,
                }
                channel = f"mpesa:payment:{checkout_request_id}"
                await redis_manager.client.publish(channel, json.dumps(event_payload))
                logger.info(f"Published status update to Redis for {checkout_request_id}")
            except Exception as publish_error:
                logger.error(f"Failed to publish status update to Redis: {publish_error}")
        
        metrics_registry.increment_counter("mpesa_callbacks_total", labels={"status": tx_status})
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error committing transaction status update: {e}")
        return {"ResultCode": 1, "ResultDesc": "Database commit failed"}

    return {"ResultCode": 0, "ResultDesc": "Success"}


@router.websocket("/mpesa/ws/{checkout_request_id}")
async def mpesa_ws_endpoint(
    websocket: WebSocket,
    checkout_request_id: str,
    token: str = Query(...),
):
    # Accept connection first
    await websocket.accept()
    metrics_registry.adjust_gauge("mpesa_websocket_active_connections", 1)
    metrics_registry.increment_counter("mpesa_websocket_connections_total")
    
    # Helper to resolve DB session dynamically (supporting tests override)
    async def get_db_session():
        override_func = websocket.app.dependency_overrides.get(get_db)
        if override_func:
            async for session in override_func():
                yield session
        else:
            async with SessionLocal() as session:
                yield session

    try:
        # Decode and validate token
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            token_checkout_id = payload.get("sub")
            if token_checkout_id != checkout_request_id:
                raise ValueError("Checkout request ID mismatch")
        except Exception as auth_err:
            logger.warning(f"WebSocket auth failed for {checkout_request_id}: {auth_err}")
            metrics_registry.increment_counter("mpesa_websocket_errors_total", labels={"type": "auth_failure"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Fetch current status from DB
        transaction = None
        async for db in get_db_session():
            stmt = select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == checkout_request_id)
            res = await db.execute(stmt)
            transaction = res.scalars().first()
            
        if not transaction:
            logger.warning(f"Transaction {checkout_request_id} not found in DB")
            metrics_registry.increment_counter("mpesa_websocket_errors_total", labels={"type": "not_found"})
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return

        # Send current state
        initial_payload = {
            "status": transaction.status,
            "checkout_request_id": transaction.checkout_request_id,
            "amount": transaction.amount,
            "phone_number": transaction.phone_number,
            "mpesa_receipt_number": transaction.mpesa_receipt_number,
            "result_desc": transaction.result_desc,
        }
        await websocket.send_json(initial_payload)

        # If transaction is already resolved, close WS immediately
        if transaction.status in ("completed", "failed"):
            await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
            return

        # Setup subscription / fallback
        channel_name = f"mpesa:payment:{checkout_request_id}"
        redis_listener_task = None

        async def send_ws_json_safe(data):
            try:
                await websocket.send_json(data)
            except Exception:
                pass

        if redis_manager.client:
            pubsub = redis_manager.client.pubsub()
            await pubsub.subscribe(channel_name)

            async def redis_listener():
                try:
                    async for msg in pubsub.listen():
                        if msg["type"] == "message":
                            event_data = json.loads(msg["data"])
                            await send_ws_json_safe(event_data)
                            if event_data.get("status") in ("completed", "failed"):
                                break
                except asyncio.CancelledError:
                    pass
                except Exception as err:
                    logger.error(f"Error in Redis listener for {checkout_request_id}: {err}")
                    metrics_registry.increment_counter("mpesa_websocket_errors_total", labels={"type": "redis_listener_error"})
                finally:
                    try:
                        await pubsub.unsubscribe(channel_name)
                        await pubsub.aclose()
                    except Exception:
                        pass

            redis_listener_task = asyncio.create_task(redis_listener())
        else:
            logger.warning(f"Redis client not available, using DB polling for WS {checkout_request_id}")
            async def db_polling():
                try:
                    while True:
                        await asyncio.sleep(2.0)
                        async for db_ctx in get_db_session():
                            tx_stmt = select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == checkout_request_id)
                            tx_res = await db_ctx.execute(tx_stmt)
                            tx = tx_res.scalars().first()
                            if tx and tx.status != "pending":
                                poll_payload = {
                                    "status": tx.status,
                                    "checkout_request_id": tx.checkout_request_id,
                                    "amount": tx.amount,
                                    "phone_number": tx.phone_number,
                                    "mpesa_receipt_number": tx.mpesa_receipt_number,
                                    "result_desc": tx.result_desc,
                                }
                                await send_ws_json_safe(poll_payload)
                                return
                except asyncio.CancelledError:
                    pass
                except Exception as err:
                    logger.error(f"Error in DB polling fallback for {checkout_request_id}: {err}")
                    metrics_registry.increment_counter("mpesa_websocket_errors_total", labels={"type": "db_polling_error"})

            redis_listener_task = asyncio.create_task(db_polling())

        # Main read loop to keep connection alive and detect client disconnects/pings
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    parsed = json.loads(data)
                    if parsed.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except ValueError:
                    pass
        except WebSocketDisconnect:
            logger.info(f"WebSocket client disconnected for {checkout_request_id}")
        except Exception as e:
            logger.error(f"WebSocket error in read loop for {checkout_request_id}: {e}")
            metrics_registry.increment_counter("mpesa_websocket_errors_total", labels={"type": "ws_connection_error"})
        finally:
            if redis_listener_task:
                redis_listener_task.cancel()
                try:
                    await redis_listener_task
                except asyncio.CancelledError:
                    pass
    finally:
        metrics_registry.adjust_gauge("mpesa_websocket_active_connections", -1)
