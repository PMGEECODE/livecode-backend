from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from uuid import UUID
from pydantic import BaseModel
from app import crud, schemas, models
from app.api import deps

router = APIRouter()

class StatusUpdate(BaseModel):
    status: str

class RoleUpdate(BaseModel):
    role: str

@router.get("/", response_model=schemas.UserPaginated)
async def read_users(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 20,
    role: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: models.User = Depends(deps.check_permission("view_users")),
) -> Any:
    """
    Retrieve users with pagination and filters.
    """
    query = select(models.User)
    
    # Apply filters
    if role:
        query = query.filter(models.User.role == role)
    if status:
        query = query.filter(models.User.status == status)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                models.User.email.ilike(search_term),
                models.User.full_name.ilike(search_term),
                models.User.first_name.ilike(search_term),
                models.User.last_name.ilike(search_term),
                models.User.username.ilike(search_term),
            )
        )
        
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated items
    query = query.order_by(models.User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()
    
    return {"users": users, "total": total}

@router.post("/", response_model=schemas.User)
async def create_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: schemas.UserCreate,
    current_user: models.User = Depends(deps.check_permission("manage_users")),
) -> Any:
    """
    Create new user.
    """
    user = await crud.user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    
    if not user_in.full_name and (user_in.first_name or user_in.last_name):
        user_in.full_name = f"{user_in.first_name or ''} {user_in.last_name or ''}".strip()
        
    return await crud.user.create(db, obj_in=user_in)

@router.get("/me", response_model=schemas.UserMe)
async def read_user_me(
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get current user profile including roles and permissions.
    """
    permissions = deps.get_user_permissions(current_user)
    user_data = schemas.User.model_validate(current_user)
    return schemas.UserMe(
        **user_data.model_dump(),
        permissions=permissions
    )

@router.get("/{user_id}", response_model=schemas.User)
async def read_user_by_id(
    user_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("view_users")),
) -> Any:
    """
    Get a specific user by id.
    """
    user = await crud.user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    return user

@router.put("/{user_id}", response_model=schemas.User)
async def update_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_id: UUID,
    user_in: schemas.UserUpdate,
    current_user: models.User = Depends(deps.check_permission("manage_users")),
) -> Any:
    """
    Update a user.
    """
    user = await crud.user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
        
    if not user_in.full_name and (user_in.first_name or user_in.last_name):
        user_in.full_name = f"{user_in.first_name or ''} {user_in.last_name or ''}".strip()
        
    return await crud.user.update(db, db_obj=user, obj_in=user_in)

@router.delete("/{user_id}", response_model=schemas.User)
async def delete_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_id: UUID,
    current_user: models.User = Depends(deps.check_permission("manage_users")),
) -> Any:
    """
    Delete a user.
    """
    user = await crud.user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    return await crud.user.remove(db, id=user_id)

@router.patch("/{user_id}/status", response_model=schemas.User)
async def change_user_status(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_id: UUID,
    status_in: StatusUpdate,
    current_user: models.User = Depends(deps.check_permission("manage_users")),
) -> Any:
    """
    Update user status.
    """
    user = await crud.user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    user.status = status_in.status
    if status_in.status == "inactive":
        user.is_active = False
    elif status_in.status == "active":
        user.is_active = True
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.patch("/{user_id}/role", response_model=schemas.User)
async def change_user_role(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_id: UUID,
    role_in: RoleUpdate,
    current_user: models.User = Depends(deps.check_permission("manage_users")),
) -> Any:
    """
    Update user role.
    """
    user = await crud.user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    
    role = role_in.role.strip().lower()
    valid_roles = {"admin", "user", "moderator", "instructor"}
    if role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )

    user.role = role
    if role == "admin":
        user.is_superuser = True
    else:
        user.is_superuser = False
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

import secrets
from datetime import datetime, timezone, timedelta
from app.db.models.user_invite import UserInvite
from app.core.email import send_email_async
from fastapi import Request

@router.post("/invite", status_code=201)
async def invite_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    invite_in: schemas.UserInviteCreate,
    request: Request,
    current_user: models.User = Depends(deps.check_permission("manage_users")),
) -> Any:
    """
    Invite a new user to join as a team member.
    """
    # Check if user already exists
    existing_user = await crud.user.get_by_email(db, email=invite_in.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists in the system."
        )

    # Check if active invite already exists
    query = select(UserInvite).filter(
        UserInvite.email == invite_in.email,
        UserInvite.is_used == False
    )
    res = await db.execute(query)
    existing_invites = res.scalars().all()
    
    now = datetime.now(timezone.utc)
    for existing_invite in existing_invites:
        exp = existing_invite.expires_at
        is_exp = exp < now if exp.tzinfo is not None else exp < now.replace(tzinfo=None)
        if not is_exp:
            await db.delete(existing_invite)
    await db.commit()

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invite = UserInvite(
        email=invite_in.email,
        role=invite_in.role,
        token=token,
        expires_at=expires_at
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    origin = request.headers.get("origin")
    if not origin:
        origin = str(request.base_url).rstrip("/")
        
    setup_link = f"{origin}/setup-account?token={token}"

    email_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #001A4D;">Welcome to Livecode Technologies</h2>
        <p>Hello,</p>
        <p>You have been invited to join the Livecode Technologies admin panel as <strong>{invite_in.role}</strong>.</p>
        <p>Please click the button below to set up your account credentials:</p>
        <div style="margin: 30px 0; text-align: center;">
            <a href="{setup_link}" style="background-color: #F58220; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Set Up Account</a>
        </div>
        <p>Or copy and paste this URL into your browser:</p>
        <p style="word-break: break-all; color: #F58220;">{setup_link}</p>
        <p>This invitation link will expire in 7 days.</p>
        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;" />
        <p style="font-size: 12px; color: #777777;">If you were not expecting this invitation, please ignore this email.</p>
    </body>
    </html>
    """
    
    await send_email_async(
        to_email=invite_in.email,
        subject="Invitation to join Livecode Technologies Admin Panel",
        html_body=email_html
    )

    return {"status": "success", "message": "Invitation sent successfully"}


@router.get("/invite/verify", response_model=schemas.UserInviteVerifyResponse)
async def verify_invite_token(
    *,
    db: AsyncSession = Depends(deps.get_db),
    token: str,
) -> Any:
    """
    Verify invitation token.
    """
    query = select(UserInvite).filter(UserInvite.token == token)
    res = await db.execute(query)
    invite = res.scalars().first()

    now = datetime.now(timezone.utc)
    if invite:
        exp = invite.expires_at
        is_expired = exp < now if exp.tzinfo is not None else exp < now.replace(tzinfo=None)
    else:
        is_expired = True

    if not invite or invite.is_used or is_expired:
        raise HTTPException(
            status_code=400,
            detail="Invitation link is invalid or has expired."
        )

    return {"email": invite.email, "role": invite.role}


@router.post("/invite/complete")
async def complete_invite_signup(
    *,
    db: AsyncSession = Depends(deps.get_db),
    signup_in: schemas.UserInviteComplete,
) -> Any:
    """
    Complete account setup using invitation token.
    """
    query = select(UserInvite).filter(UserInvite.token == signup_in.token)
    res = await db.execute(query)
    invite = res.scalars().first()

    now = datetime.now(timezone.utc)
    if invite:
        exp = invite.expires_at
        is_expired = exp < now if exp.tzinfo is not None else exp < now.replace(tzinfo=None)
    else:
        is_expired = True

    if not invite or invite.is_used or is_expired:
        raise HTTPException(
            status_code=400,
            detail="Invitation link is invalid or has expired."
        )

    existing_user = await crud.user.get_by_email(db, email=invite.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists in the system."
        )

    full_name = f"{signup_in.first_name} {signup_in.last_name}".strip()

    user_in = schemas.UserCreate(
        email=invite.email,
        password=signup_in.password,
        first_name=signup_in.first_name,
        last_name=signup_in.last_name,
        full_name=full_name,
        username=signup_in.username or invite.email.split("@")[0],
        phone=signup_in.phone,
        role=invite.role,
        status="active",
        is_active=True,
        is_superuser=True if invite.role == "admin" else False,
        is_verified=True
    )
    
    new_user = await crud.user.create(db, obj_in=user_in)

    invite.is_used = True
    db.add(invite)
    await db.commit()

    return {"status": "success", "message": "Account setup completed successfully"}

