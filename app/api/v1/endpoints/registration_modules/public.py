import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.limiter import limiter
from app.core.redis import redis_manager
from app.crud.course import course as crud_course
from app.crud.registration import create_registration
from app.schemas.registration import RegistrationCreate, RegistrationResponse
from app.api.v1.endpoints.registration_modules.emails import process_registration_email
from app.services.payment_options import ensure_payment_provider_enabled, normalize_payment_provider

router = APIRouter()


@router.post(
    "/",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a course registration",
)
@limiter.limit("5/minute")
async def submit_registration(
    request: Request,
    response: Response,
    payload: RegistrationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RegistrationResponse:
    """
    Submit an individual or group course registration.
    
    - Validates all input fields strictly (extra fields rejected).
    - Persists registration to the database.
    - Generates attachments and sends an email in the background.
    - Returns the created registration record.
    """
    provider = normalize_payment_provider(payload.payment_method)
    if provider == "offline":
        await ensure_payment_provider_enabled(db, provider)

    # Validate that the course actually exists before attempting insertion
    course_dict = None
    if payload.course_id:
        try:
            parsed_id = uuid.UUID(payload.course_id)
            course = await crud_course.get(db=db, id=parsed_id)
            if not course:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The selected course does not exist.",
                )
            
            # Serialize course info for the background task
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
                    "price_kes": float(course.logistics.price_kes) if course.logistics.price_kes else 0.0,
                }
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid course ID format.",
            )

    try:
        registration = await create_registration(db=db, payload=payload)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process registration. Please try again.",
        )

    # Serialize registration for the background task
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
    }

    # Only send invoice/confirmation email on submission if this is an Offline registration.
    # For online payments, the email is deferred until the payment transaction completes.
    if payload.payment_method == "Offline":
        background_tasks.add_task(process_registration_email, reg_dict, course_dict)

    # Invalidate dashboard and registrations cache
    await redis_manager.delete_pattern("dashboard:*")
    await redis_manager.delete_pattern("registrations:*")

    return RegistrationResponse(
        id=str(registration.id),
        status=registration.status,
        course_title=registration.course_title,
        registration_type=registration.registration_type,
        first_name=registration.first_name,
        last_name=registration.last_name,
        email=registration.email,
        currency=registration.currency,
    )
