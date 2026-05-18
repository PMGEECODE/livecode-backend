from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import uuid
from typing import Any, List
import sqlalchemy as sa
from app.api import deps
from app.api.deps import get_db
from app.schemas.registration import RegistrationCreate, RegistrationResponse
from app.crud.registration import create_registration
from app.db.models.registration import CourseRegistration
from app.db.models.course import Course
from app.core.document_generators import (
    generate_invoice_pdf,
    generate_invitation_letter_pdf,
    generate_pre_training_form_docx
)

router = APIRouter()

@router.get("/fix-db")
async def fix_db(db: AsyncSession = Depends(get_db)) -> Any:
    """Temporary endpoint to create the course_registration table on production."""
    try:
        sql = sa.text('''
        CREATE TABLE IF NOT EXISTS course_registration (
            id UUID NOT NULL PRIMARY KEY,
            course_id UUID,
            course_title VARCHAR NOT NULL,
            schedule_date VARCHAR,
            schedule_location VARCHAR,
            registration_type VARCHAR NOT NULL,
            title VARCHAR,
            first_name VARCHAR NOT NULL,
            middle_name VARCHAR,
            last_name VARCHAR NOT NULL,
            gender VARCHAR,
            organization VARCHAR,
            department VARCHAR,
            phone VARCHAR,
            email VARCHAR NOT NULL,
            official_email VARCHAR,
            country VARCHAR,
            city VARCHAR,
            address VARCHAR,
            how_heard VARCHAR,
            accommodation BOOLEAN,
            airport_pickup BOOLEAN,
            additional_info TEXT,
            group_size VARCHAR,
            group_members_json TEXT,
            status VARCHAR NOT NULL,
            FOREIGN KEY(course_id) REFERENCES course (id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS ix_course_registration_course_id ON course_registration (course_id);
        CREATE INDEX IF NOT EXISTS ix_course_registration_email ON course_registration (email);
        ''')
        await db.execute(sql)
        await db.commit()
        
        # Also fix the alembic version
        try:
            await db.execute(sa.text("UPDATE alembic_version SET version_num = '9e49804f78bb'"))
            await db.commit()
        except Exception:
            pass
            
        return {"message": "course_registration table created successfully! You can now submit registrations."}
    except Exception as e:
        await db.rollback()
        return {"error": str(e)}


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
    # Validate that the course actually exists before attempting insertion
    if payload.course_id:
        import uuid
        from app.crud.course import course as crud_course
        try:
            parsed_id = uuid.UUID(payload.course_id)
            course = await crud_course.get(db=db, id=parsed_id)
            if not course:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The selected course does not exist.",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid course ID format.",
            )

    try:
        registration = await create_registration(db=db, payload=payload)
    except Exception as e:
        import logging
        logging.error(f"Registration Error: {e}")
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


@router.get(
    "/{id}/invoice",
    summary="Download dynamically generated registration invoice PDF",
)
async def download_invoice(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Generate and stream a professional 3-page Invoice PDF for a course registration.
    """
    result = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == id))
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
        
    course = None
    if registration.course_id:
        course_res = await db.execute(
            select(Course)
            .options(selectinload(Course.logistics))
            .filter(Course.id == registration.course_id)
        )
        course = course_res.scalars().first()
        
    pdf_buffer = generate_invoice_pdf(registration, course)
    filename = f"Invoice_{registration.first_name}_{registration.last_name}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get(
    "/{id}/invitation-letter",
    summary="Download dynamically generated registration invitation letter PDF",
)
async def download_invitation_letter(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Generate and stream a professional 6-page Invitation Letter PDF with syllabus for a course registration.
    """
    result = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == id))
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
        
    course = None
    if registration.course_id:
        course_res = await db.execute(
            select(Course)
            .options(selectinload(Course.logistics))
            .filter(Course.id == registration.course_id)
        )
        course = course_res.scalars().first()
        
    pdf_buffer = generate_invitation_letter_pdf(registration, course)
    filename = f"Invitation_Letter_{registration.first_name}_{registration.last_name}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get(
    "/{id}/pre-training-form",
    summary="Download dynamically generated pre-training evaluation form DOCX",
)
async def download_pre_training_form(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Generate and stream a professional Word DOCX Pre-Training assessment form for a course registration.
    """
    result = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == id))
    registration = result.scalars().first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
        
    course = None
    if registration.course_id:
        course_res = await db.execute(
            select(Course)
            .options(selectinload(Course.logistics))
            .filter(Course.id == registration.course_id)
        )
        course = course_res.scalars().first()
        
    docx_buffer = generate_pre_training_form_docx(registration, course)
    filename = f"Pre_Training_Form_{registration.first_name}_{registration.last_name}.docx"
    
    return StreamingResponse(
        docx_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

