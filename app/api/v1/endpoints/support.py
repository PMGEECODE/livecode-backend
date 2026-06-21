import asyncio
import json
import logging
import uuid
import os
import anyio
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, File, UploadFile, Request
import html
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.redis import redis_manager
from app.core.sse import sse_manager
from app import schemas, models, crud
from app.api import deps

def sanitize_text(text: str) -> str:
    escaped = html.escape(text.strip())
    profanities = ["slur1", "slur2"]
    for p in profanities:
        escaped = escaped.replace(p, "****")
    return escaped

logger = logging.getLogger(__name__)
router = APIRouter()

oauth2_optional = OAuth2PasswordBearer(
    tokenUrl=f"/api/v1/auth/login",
    auto_error=False
)

async def get_current_user_optional(
    db: AsyncSession = Depends(deps.get_db),
    token: Optional[str] = Depends(oauth2_optional)
) -> Optional[models.User]:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        sub = payload.get("sub")
        if not sub:
            return None
        user_id = uuid.UUID(sub)
        user = await crud.user.get(db, id=user_id)
        return user
    except Exception:
        return None

async def simulate_agent_reply(session_id: str, user_message: str):
    """
    Background task to simulate a real-time agent typing and responding.
    """
    # Wait 1.5 seconds to simulate agent typing
    await asyncio.sleep(1.5)
    
    meta_raw = await redis_manager.get(f"support:session:{session_id}:meta")
    if not meta_raw:
        return
        
    try:
        meta = json.loads(meta_raw)
    except Exception:
        return
        
    if meta.get("status") != "active" or meta.get("agent_takeover") or meta.get("auto_reply_sent"):
        return
        
    topic = meta.get("topic", "general").lower()
    query = user_message.lower()
    
    if topic == "technical":
        if "login" in query or "password" in query or "sign in" in query:
            reply_text = "To reset your password, please click on the 'Forgot Password' link on the login page. An email with reset instructions will be sent to your registered address."
        elif "error" in query or "bug" in query or "broken" in query:
            reply_text = "I'm sorry to hear that. Could you please specify the error message or screenshot if possible? You can also email support@livecodetechnologies.com."
        elif "hello" in query or "hi" in query or "hey" in query:
            reply_text = f"Hello {meta.get('user_name')}! Thank you for contacting Technical Support. How can I help you today?"
        else:
            reply_text = "Thank you for reaching out to Technical Support. An engineer is reviewing your query. In the meantime, please check our FAQ section on common issues."
    elif topic == "business":
        if "price" in query or "cost" in query or "fee" in query or "invoice" in query or "payment" in query or "quote" in query:
            reply_text = "For business inquiries, payments, or custom quotes, our finance and sales department will get back to you within 30 minutes with the billing details."
        elif "hello" in query or "hi" in query or "hey" in query:
            reply_text = f"Hello {meta.get('user_name')}! Thank you for contacting Business Support. How can I help you today?"
        else:
            reply_text = "Thank you for reaching out to Business Support. Our business development team is reviewing your query and will reply shortly."
    elif topic == "guidance":
        if "course" in query or "training" in query or "enroll" in query:
            reply_text = "You can enroll in any upcoming training course by visiting our Training Calendar page, selecting your course, and completing the registration form."
        elif "hello" in query or "hi" in query or "hey" in query:
            reply_text = f"Hello {meta.get('user_name')}! Thank you for contacting Training Guidance. How can I help you today?"
        else:
            reply_text = "Thank you for reaching out to Training Guidance. Our advisors are routing your inquiry to the best consultant."
    else:
        # General / default topic responses
        if "hello" in query or "hi" in query or "hey" in query:
            reply_text = f"Hello {meta.get('user_name')}! Thank you for contacting LiveCode Instant Support. How can I help you today?"
        else:
            reply_text = "Thank you for reaching out. An agent is reviewing your query. In the meantime, please check our FAQ section on common issues."
        
    msg_id = uuid.uuid4()
    agent_msg = {
        "id": str(msg_id),
        "sender": "agent",
        "message": reply_text,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    messages_raw = await redis_manager.get(f"support:session:{session_id}:messages")
    messages = json.loads(messages_raw) if messages_raw else []
    messages.append(agent_msg)
    await redis_manager.set(f"support:session:{session_id}:messages", json.dumps(messages), expire=86400)
    
    meta["auto_reply_sent"] = True
    await redis_manager.set(f"support:session:{session_id}:meta", json.dumps(meta), expire=86400)
    
    # Broadcast to SSE subscribers
    await sse_manager.broadcast("support_message", {
        "session_id": session_id,
        "message": agent_msg
    })

@router.post("/sessions", response_model=schemas.SupportSessionResponse)
async def create_session(
    session_in: schemas.SupportSessionCreate,
    request: Request
) -> Any:
    """
    Initialize a new real-time support session.
    """
    if not redis_manager.client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis service not available for real-time support"
        )
        
    # Rate limit: max 3 session initializations per hour per IP
    client_ip = request.client.host if request.client else "unknown"
    ip_key = f"support:rate_limit:session:{client_ip}"
    sessions_count = await redis_manager.client.incr(ip_key)
    if sessions_count == 1:
        await redis_manager.client.expire(ip_key, 3600)
    elif sessions_count > 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many support requests. Please try again in an hour."
        )
        
    session_id = uuid.uuid4()
    meta = {
        "session_id": str(session_id),
        "user_name": sanitize_text(session_in.user_name),
        "user_email": sanitize_text(session_in.user_email),
        "topic": sanitize_text(session_in.topic),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Save session metadata and empty messages array to Redis (expires in 24 hours)
    await redis_manager.set(f"support:session:{session_id}:meta", json.dumps(meta), expire=86400)
    await redis_manager.set(f"support:session:{session_id}:messages", json.dumps([]), expire=86400)
    
    # Broadcast session initialization
    await sse_manager.broadcast("support_session_started", meta)
    
    return schemas.SupportSessionResponse(
        session_id=session_id,
        user_name=meta["user_name"],
        user_email=meta["user_email"],
        topic=meta["topic"],
        status=meta["status"],
        created_at=datetime.fromisoformat(meta["created_at"])
    )


@router.post("/sessions/{session_id}/messages", response_model=schemas.SupportMessageResponse)
async def send_message(
    session_id: uuid.UUID,
    message_in: schemas.SupportMessageCreate,
    background_tasks: BackgroundTasks,
    current_user: Optional[models.User] = Depends(get_current_user_optional)
) -> Any:
    """
    Send a message within an active support session.
    """
    if not redis_manager.client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis service not available for real-time support"
        )
        
    meta_raw = await redis_manager.get(f"support:session:{session_id}:meta")
    if not meta_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support session not found or expired"
        )
        
    meta = json.loads(meta_raw)
    if meta.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Support session is closed"
        )
        
    # Rate limit messages per session (1 message per second for user)
    if message_in.sender == "user":
        rate_key = f"support:rate_limit:msg:{session_id}"
        is_limited = await redis_manager.client.set(rate_key, "1", ex=1, nx=True)
        if not is_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait a second before sending another message."
            )
        
    msg_id = uuid.uuid4()
    msg = {
        "id": str(msg_id),
        "sender": message_in.sender,
        "message": sanitize_text(message_in.message),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    messages_raw = await redis_manager.get(f"support:session:{session_id}:messages")
    messages = json.loads(messages_raw) if messages_raw else []
    messages.append(msg)
    
    await redis_manager.set(f"support:session:{session_id}:messages", json.dumps(messages), expire=86400)
    
    # Broadcast to SSE subscribers
    await sse_manager.broadcast("support_message", {
        "session_id": str(session_id),
        "message": msg
    })
    
    # If the sender is an agent, mark session as taken over to stop automatic simulation
    if message_in.sender == "agent":
        meta["agent_takeover"] = True
        agent_name = "Admin Support"
        if current_user:
            agent_name = current_user.full_name or current_user.username
        meta["agent_name"] = agent_name
        await redis_manager.set(f"support:session:{session_id}:meta", json.dumps(meta), expire=86400)
        await sse_manager.broadcast("support_agent_takeover", {
            "session_id": str(session_id),
            "agent_name": agent_name
        })
    
    # Trigger AI simulation in the background if the message was sent by user
    if message_in.sender == "user":
        background_tasks.add_task(simulate_agent_reply, str(session_id), message_in.message)
        
    return schemas.SupportMessageResponse(
        id=msg_id,
        sender=msg["sender"],
        message=msg["message"],
        created_at=datetime.fromisoformat(msg["created_at"])
    )

@router.get("/sessions", response_model=List[schemas.SupportSessionResponse])
async def list_active_sessions() -> Any:
    """
    List all active support sessions. (Mainly for Admins/Support Staff)
    """
    if not redis_manager.client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis service not available for real-time support"
        )
        
    active_sessions = []
    cursor = 0
    while True:
        cursor, keys = await redis_manager.client.scan(cursor=cursor, match="support:session:*:meta", count=100)
        for key in keys:
            meta_raw = await redis_manager.get(key)
            if meta_raw:
                meta = json.loads(meta_raw)
                active_sessions.append(
                    schemas.SupportSessionResponse(
                        session_id=uuid.UUID(meta["session_id"]),
                        user_name=meta["user_name"],
                        user_email=meta["user_email"],
                        topic=meta.get("topic", "general"),
                        status=meta["status"],
                        created_at=datetime.fromisoformat(meta["created_at"]),
                        agent_takeover=meta.get("agent_takeover", False),
                        agent_name=meta.get("agent_name")
                    )
                )
        if cursor == 0:
            break
            
    active_sessions.sort(key=lambda x: x.created_at, reverse=True)
    return active_sessions


@router.get("/sessions/{session_id}", response_model=schemas.SupportSessionResponse)
async def get_session(session_id: uuid.UUID) -> Any:
    """
    Retrieve session details.
    """
    if not redis_manager.client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis service not available for real-time support"
        )
        
    meta_raw = await redis_manager.get(f"support:session:{session_id}:meta")
    if not meta_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support session not found or expired"
        )
        
    meta = json.loads(meta_raw)
    return schemas.SupportSessionResponse(
        session_id=session_id,
        user_name=meta["user_name"],
        user_email=meta["user_email"],
        topic=meta.get("topic", "general"),
        status=meta["status"],
        created_at=datetime.fromisoformat(meta["created_at"]),
        agent_takeover=meta.get("agent_takeover", False),
        agent_name=meta.get("agent_name")
    )


@router.get("/sessions/{session_id}/messages", response_model=List[schemas.SupportMessageResponse])
async def read_messages(session_id: uuid.UUID) -> Any:
    """
    Retrieve all messages for a specific support session.
    """
    if not redis_manager.client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis service not available for real-time support"
        )
        
    meta_raw = await redis_manager.get(f"support:session:{session_id}:meta")
    if not meta_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support session not found or expired"
        )
        
    messages_raw = await redis_manager.get(f"support:session:{session_id}:messages")
    messages = json.loads(messages_raw) if messages_raw else []
    
    return [
        schemas.SupportMessageResponse(
            id=uuid.UUID(msg["id"]),
            sender=msg["sender"],
            message=msg["message"],
            created_at=datetime.fromisoformat(msg["created_at"])
        )
        for msg in messages
    ]

@router.post("/sessions/{session_id}/close", response_model=schemas.SupportSessionResponse)
async def close_session(session_id: uuid.UUID) -> Any:
    """
    Close an active support session.
    """
    if not redis_manager.client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis service not available for real-time support"
        )
        
    meta_raw = await redis_manager.get(f"support:session:{session_id}:meta")
    if not meta_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support session not found or expired"
        )
        
    meta = json.loads(meta_raw)
    meta["status"] = "closed"
    
    await redis_manager.set(f"support:session:{session_id}:meta", json.dumps(meta), expire=86400)
    
    # Broadcast closure
    await sse_manager.broadcast("support_session_closed", meta)
    
    return schemas.SupportSessionResponse(
        session_id=session_id,
        user_name=meta["user_name"],
        user_email=meta["user_email"],
        topic=meta.get("topic", "general"),
        status=meta["status"],
        created_at=datetime.fromisoformat(meta["created_at"]),
        agent_takeover=meta.get("agent_takeover", False),
        agent_name=meta.get("agent_name")
    )


@router.post("/sessions/{session_id}/typing")
async def send_typing_status(
    session_id: uuid.UUID,
    payload: schemas.SupportTypingPayload,
    current_user: Optional[models.User] = Depends(get_current_user_optional)
) -> Any:
    """
    Broadcast typing status of user or agent.
    """
    agent_name = None
    if payload.sender == "agent":
        if current_user:
            agent_name = current_user.full_name or current_user.username
        else:
            agent_name = "Admin Support"
            
    await sse_manager.broadcast("support_typing", {
        "session_id": str(session_id),
        "sender": payload.sender,
        "typing": payload.typing,
        "agent_name": agent_name
    })
    return {"status": "ok"}


@router.post("/sessions/{session_id}/upload-image", response_model=dict)
async def upload_support_image(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
) -> dict:
    """
    Upload an image to an active support session.
    * Validates session activity.
    * Enforces image signature and re-encoding to WebP.
    * Returns the secure media endpoint URL.
    """
    from app.core.upload_security import (
        read_upload_file_limited,
        validate_image_upload,
        convert_image_to_webp,
        upload_root,
    )

    # 1. Verify active session exists in Redis
    session_key = f"support:session:{session_id}:meta"
    session_data = await redis_manager.get(session_key)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active support session not found"
        )
        
    try:
        meta = json.loads(session_data)
        if meta.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Support session is closed"
            )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session metadata"
        )

    # 2. Read, size-limit, validate, and convert image to WebP
    data = await read_upload_file_limited(file, settings.IMAGE_UPLOAD_MAX_BYTES)
    ext = validate_image_upload(file, data)
    webp_data = await anyio.to_thread.run_sync(lambda: convert_image_to_webp(data, ext))

    from app.services.vercel_blob import upload_product_image_blob

    # 3. Save file as safe UUID WebP directly to Vercel Blob
    filename = f"support/{uuid.uuid4()}.webp"

    public_url = await upload_product_image_blob(
        pathname=filename,
        data=webp_data,
        content_type="image/webp",
    )

    # 4. Return accessible media URL from Vercel Blob
    return {"url": public_url}
