from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from typing import Any, List
from app.api import deps
from app.api.deps import get_db
from app.schemas.registration import RegistrationCreate, RegistrationResponse
from app.crud.registration import create_registration
from app.db.models.registration import CourseRegistration

router = APIRouter()


@router.post(
    "/",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a course registration",
)
async def submit_registration(
    payload: RegistrationCreate,
    db: AsyncSession = Depends(get_db),
) -> RegistrationResponse:
    """
    Submit an individual or group course registration.
    
    - Validates all input fields strictly (extra fields rejected).
    - Persists registration to the database.
    - Returns the created registration record.
    """
    try:
        registration = await create_registration(db=db, payload=payload)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process registration. Please try again.",
        )

    return RegistrationResponse(
        id=str(registration.id),
        status=registration.status,
        course_title=registration.course_title,
        registration_type=registration.registration_type,
        first_name=registration.first_name,
        last_name=registration.last_name,
        email=registration.email,
    )


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
    result = await db.execute(
        select(CourseRegistration)
        .order_by(CourseRegistration.id.desc())
        .offset(skip)
        .limit(limit)
    )
    regs = result.scalars().all()
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
    return {"message": "Registration deleted successfully"}

