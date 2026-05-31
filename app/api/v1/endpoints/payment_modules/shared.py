import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.course import Course
from app.db.models.registration import CourseRegistration


def calculate_registration_total(registration: CourseRegistration, course: Course) -> float:
    """
    Calculates the exact course price (including VAT) based on backend database
    records. This acts as the source of truth for payment verification.
    Returns the total price in USD.
    """
    currency = registration.currency or "USD"
    
    # 1. Look for a matching schedule
    matched_schedule = None
    if course.schedules:
        for s in course.schedules:
            if s.date_range == registration.schedule_date and s.location == registration.schedule_location:
                matched_schedule = s
                break

    # 2. Determine base unit price
    if currency == "KES":
        unit_price = None
        if matched_schedule and matched_schedule.price_kes:
            unit_price = matched_schedule.price_kes
        elif course.logistics and course.logistics.price_kes:
            unit_price = course.logistics.price_kes
        
        # Fallback to USD price * 130 if KES price is not configured
        if unit_price is None:
            usd_price = None
            if matched_schedule and matched_schedule.price_usd:
                usd_price = matched_schedule.price_usd
            elif course.logistics and course.logistics.price_usd:
                usd_price = course.logistics.price_usd
            
            unit_price = (usd_price or 1500.0) * 130.0
    else: # USD
        unit_price = None
        if matched_schedule and matched_schedule.price_usd:
            unit_price = matched_schedule.price_usd
        elif course.logistics and course.logistics.price_usd:
            unit_price = course.logistics.price_usd
        
        if unit_price is None:
            unit_price = 1500.0

    # 3. Multiply by delegates/participants
    participant_count = 1
    if registration.registration_type == "group" and registration.group_size:
        try:
            participant_count = int(registration.group_size)
        except ValueError:
            participant_count = 1

    subtotal = unit_price * participant_count
    vat = subtotal * 0.16
    grand_total = subtotal + vat
    
    # Convert KES to USD for PayPal
    if currency == "KES":
        return grand_total / 130.0
    return grand_total


def calculate_registration_payment(registration: CourseRegistration, course: Course) -> tuple[float, str]:
    """
    Calculates the exact payable amount in the registration currency.
    This is the backend source of truth for card payment initialization and verification.
    """
    currency = (registration.currency or "USD").upper()

    matched_schedule = None
    if course.schedules:
        for schedule in course.schedules:
            if schedule.date_range == registration.schedule_date and schedule.location == registration.schedule_location:
                matched_schedule = schedule
                break

    if currency == "KES":
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
    else:
        currency = "USD"
        unit_price = None
        if matched_schedule and matched_schedule.price_usd:
            unit_price = matched_schedule.price_usd
        elif course.logistics and course.logistics.price_usd:
            unit_price = course.logistics.price_usd
        if unit_price is None:
            unit_price = 1500.0

    participant_count = 1
    if registration.registration_type == "group" and registration.group_size:
        try:
            participant_count = max(1, int(registration.group_size))
        except ValueError:
            participant_count = 1

    subtotal = float(unit_price) * participant_count
    grand_total = subtotal + (subtotal * 0.16)
    return round(grand_total, 2), currency


async def get_registration_course_for_payment(
    db: AsyncSession,
    registration_id: uuid.UUID,
) -> tuple[CourseRegistration, Course]:
    stmt = select(CourseRegistration).filter(CourseRegistration.id == registration_id)
    result = await db.execute(stmt)
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registration record not found.")

    course_stmt = (
        select(Course)
        .options(selectinload(Course.logistics), selectinload(Course.schedules))
        .filter(Course.id == registration.course_id)
    )
    course_result = await db.execute(course_stmt)
    course = course_result.scalars().first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated course not found.")

    return registration, course


def build_registration_email_payload(
    registration: CourseRegistration,
    payment_method: str,
) -> dict[str, Any]:
    return {
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
        "payment_method": payment_method,
        "status": "confirmed",
    }


def build_course_email_payload(course: Course | None) -> dict[str, Any] | None:
    if not course:
        return None
    course_dict: dict[str, Any] = {
        "id": str(course.id),
        "title": course.title,
    }
    if course.logistics:
        course_dict["logistics"] = {
            "location": course.logistics.location,
            "start_date": course.logistics.start_date.isoformat() if hasattr(course.logistics.start_date, "isoformat") else course.logistics.start_date,
            "end_date": course.logistics.end_date.isoformat() if hasattr(course.logistics.end_date, "isoformat") else course.logistics.end_date,
            "duration": course.logistics.duration,
            "price_usd": float(course.logistics.price_usd) if course.logistics.price_usd else 0.0,
            "price_kes": float(course.logistics.price_kes) if hasattr(course.logistics, "price_kes") and course.logistics.price_kes else 0.0,
        }
    return course_dict
