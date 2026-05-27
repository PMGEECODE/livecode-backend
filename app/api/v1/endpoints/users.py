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
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    current_user: models.User = Depends(deps.get_current_active_superuser),
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

@router.get("/{user_id}", response_model=schemas.User)
async def read_user_by_id(
    user_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    user.role = role_in.role
    if role_in.role == "admin":
        user.is_superuser = True
    else:
        user.is_superuser = False
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


