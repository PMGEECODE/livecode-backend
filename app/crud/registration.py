import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.registration import CourseRegistration
from app.schemas.registration import RegistrationCreate


async def create_registration(
    db: AsyncSession, payload: RegistrationCreate
) -> CourseRegistration:
    """Persist a new course registration to the database."""
    group_members_json: str | None = None
    if payload.group_members:
        group_members_json = json.dumps(
            [m.model_dump() for m in payload.group_members]
        )

    registration = CourseRegistration(
        course_id=payload.course_id,
        course_title=payload.course_title,
        schedule_date=payload.schedule_date,
        schedule_location=payload.schedule_location,
        registration_type=payload.registration_type,
        title=payload.title,
        first_name=payload.first_name,
        middle_name=payload.middle_name,
        last_name=payload.last_name,
        gender=payload.gender,
        organization=payload.organization,
        department=payload.department,
        phone=payload.phone,
        email=str(payload.email),
        official_email=str(payload.official_email) if payload.official_email else None,
        country=payload.country,
        city=payload.city,
        address=payload.address,
        how_heard=payload.how_heard,
        accommodation=payload.accommodation,
        airport_pickup=payload.airport_pickup,
        additional_info=payload.additional_info,
        group_size=payload.group_size,
        group_members_json=group_members_json,
        status="pending",
    )
    db.add(registration)
    await db.commit()
    await db.refresh(registration)
    return registration
