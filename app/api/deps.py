from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from app import crud, models, schemas
from app.core import security
from app.core.config import settings
from app.db.session import SessionLocal

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)

async def get_db() -> AsyncGenerator:
    async with SessionLocal() as db:
        yield db

import uuid
from datetime import datetime, timezone

async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> models.User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        token_data = schemas.TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not token_data.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        user_id = uuid.UUID(token_data.sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: invalid subject UUID format",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user = await crud.user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Active session verification
    if not token_data.sid or user.active_session_id != token_data.sid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or was terminated from another device",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if user.session_expires_at:
        now = datetime.now(timezone.utc)
        expires = user.session_expires_at
        if expires.tzinfo is None:
            now = datetime.utcnow()
        if now > expires:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    return user

def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_active_superuser(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    role = (getattr(current_user, "role", None) or "").strip().lower()
    if current_user.is_superuser or role == "admin":
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="The user doesn't have enough privileges"
    )

def get_current_active_admin(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    """Require an active administrator account.

    Some admin-facing endpoints use the semantic name `admin`, while older
    endpoints use `superuser`. Keep both dependencies available and enforce
    the same fail-closed privilege check at the backend.
    """
    role = (getattr(current_user, "role", None) or "").strip().lower()
    if current_user.is_superuser or role == "admin":
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="The user doesn't have enough privileges",
    )


ROLE_PERMISSIONS = {
    "admin": [
        "view_performance_metrics",
        "view_overview",
        "view_analytics",
        "view_courses",
        "manage_courses",
        "delete_courses",
        "view_registrations",
        "manage_registrations",
        "view_services",
        "manage_services",
        "view_products",
        "manage_products",
        "view_blog",
        "manage_blog",
        "view_contacts",
        "manage_contacts",
        "view_assistance",
        "manage_assistance",
        "view_newsletters",
        "manage_newsletters",
        "view_partners",
        "manage_partners",
        "view_trainers",
        "manage_trainers",
        "view_payments",
        "manage_payments",
        "view_transactions",
        "export_transactions",
        "manage_refunds_disputes",
        "view_customers",
        "manage_customers",
        "view_users",
        "manage_users",
    ],
    "moderator": [
        "view_performance_metrics",
        "view_overview",
        "view_analytics",
        "view_courses",
        "manage_courses",
        "view_registrations",
        "manage_registrations",
        "view_services",
        "manage_services",
        "view_products",
        "manage_products",
        "view_blog",
        "manage_blog",
        "view_contacts",
        "manage_contacts",
        "view_assistance",
        "manage_assistance",
        "view_newsletters",
        "manage_newsletters",
        "view_partners",
        "manage_partners",
        "view_trainers",
        "manage_trainers",
        "view_payments",
        "manage_payments",
        "view_transactions",
        "export_transactions",
        "manage_refunds_disputes",
        "view_customers",
        "manage_customers",
        "view_users",
    ],
    "instructor": [
        "view_overview",
        "view_analytics",
        "view_courses",
        "view_registrations",
        "view_trainers",
        "view_assistance",
        "view_customers",
        "view_performance_metrics",
    ],
    "user": [
        "view_overview",
        "view_courses",
        "view_services",
        "view_products",
        "view_blog",
        "view_customers",
        "view_performance_metrics",
    ]
}


def get_user_permissions(user: models.User) -> list[str]:
    if user.is_superuser:
        return ROLE_PERMISSIONS["admin"]
    role = (user.role or "").strip().lower()
    return ROLE_PERMISSIONS.get(role, [])


def check_permission(permission: str):
    def dependency(current_user: models.User = Depends(get_current_active_user)):
        perms = get_user_permissions(current_user)
        if permission not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have the necessary permissions to access this resource."
            )
        return current_user
    return dependency

