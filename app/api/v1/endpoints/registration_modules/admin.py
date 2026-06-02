import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_db
from app.core.redis import redis_manager
from app.db.models.payment import PaymentTransaction
from app.db.models.registration import CourseRegistration

router = APIRouter()


@router.get(
    "/",
    response_model=List[Any],
    summary="Get all registrations",
)
async def read_registrations(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve all registrations in the database. Restricted to superusers.
    """
    skip = max(0, skip)
    limit = max(1, min(limit, 500))

    result = await db.execute(
        select(CourseRegistration)
        .order_by(CourseRegistration.id.desc())
        .offset(skip)
        .limit(limit)
    )
    regs = result.scalars().all()
    reg_ids = [r.id for r in regs]
    payment_map = {}
    if reg_ids:
        payment_result = await db.execute(
            select(PaymentTransaction)
            .filter(PaymentTransaction.registration_id.in_(reg_ids))
            .order_by(PaymentTransaction.created_at.desc())
        )
        for tx in payment_result.scalars().all():
            payment_map.setdefault(tx.registration_id, tx)

    return [
        {
            "id": str(r.id),
            "course_id": str(r.course_id) if r.course_id else None,
            "course_title": r.course_title,
            "schedule_date": r.schedule_date,
            "schedule_location": r.schedule_location,
            "registration_type": r.registration_type,
            "title": r.title,
            "first_name": r.first_name,
            "middle_name": r.middle_name,
            "last_name": r.last_name,
            "gender": r.gender,
            "organization": r.organization,
            "department": r.department,
            "phone": r.phone,
            "email": r.email,
            "official_email": r.official_email,
            "country": r.country,
            "city": r.city,
            "address": r.address,
            "how_heard": r.how_heard,
            "accommodation": r.accommodation,
            "airport_pickup": r.airport_pickup,
            "additional_info": r.additional_info,
            "group_size": r.group_size,
            "group_members_json": r.group_members_json,
            "status": r.status,
            "payment": (
                {
                    "provider": payment_map[r.id].provider,
                    "status": payment_map[r.id].status,
                    "amount": payment_map[r.id].amount,
                    "currency": payment_map[r.id].currency,
                    "reference": payment_map[r.id].checkout_request_id,
                    "receipt_number": payment_map[r.id].mpesa_receipt_number,
                    "message": payment_map[r.id].result_desc,
                    "paid_at": payment_map[r.id].paid_at.isoformat() if payment_map[r.id].paid_at else None,
                }
                if r.id in payment_map
                else None
            ),
        }
        for r in regs
    ]


@router.patch(
    "/{id}",
    response_model=Any,
    summary="Update a registration's status",
)
async def update_registration_status(
    id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update registration status (e.g. pending, confirmed, cancelled).
    """
    allowed_keys = {"status"}
    if set(payload) - allowed_keys:
        raise HTTPException(status_code=400, detail="Unexpected fields in request")

    result = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == id))
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    new_status = payload.get("status")
    if new_status not in ["pending", "confirmed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid status value")
        
    registration.status = new_status
    db.add(registration)
    await db.commit()
    await db.refresh(registration)
    
    # Invalidate dashboard cache
    await redis_manager.delete_pattern("dashboard:*")
    
    return {
        "id": str(registration.id),
        "status": registration.status,
        "course_title": registration.course_title,
        "registration_type": registration.registration_type,
        "first_name": registration.first_name,
        "last_name": registration.last_name,
        "email": registration.email,
    }


@router.delete(
    "/{id}",
    response_model=Any,
    summary="Delete a registration",
)
async def delete_registration(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a registration record.
    """
    result = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == id))
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
        
    await db.delete(registration)
    await db.commit()
    
    # Invalidate dashboard cache
    await redis_manager.delete_pattern("dashboard:*")
    
    return {"message": "Registration deleted successfully"}


@router.post(
    "/bulk-delete",
    response_model=Any,
    summary="Bulk delete registrations",
)
async def bulk_delete_registrations(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete multiple registrations at once.
    Expected payload: {"registration_ids": ["uuid-1", "uuid-2"]}
    """
    reg_ids = payload.get("registration_ids", [])
    if not reg_ids:
        raise HTTPException(status_code=400, detail="No registration IDs provided")
        
    # Convert string IDs to UUID objects
    try:
        uuid_list = [uuid.UUID(str(r_id)) for r_id in reg_ids]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format in registration_ids")

    # Fetch registrations to ensure they exist (optional, but good for validation)
    result = await db.execute(
        select(CourseRegistration).filter(CourseRegistration.id.in_(uuid_list))
    )
    registrations = result.scalars().all()
    
    if not registrations:
        return {"message": "No valid registrations found to delete"}

    for reg in registrations:
        await db.delete(reg)
        
    await db.commit()
    
    # Invalidate dashboard cache
    await redis_manager.delete_pattern("dashboard:*")
    
    return {"message": f"Successfully deleted {len(registrations)} registrations"}

