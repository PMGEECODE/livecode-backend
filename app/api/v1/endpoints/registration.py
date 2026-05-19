from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.limiter import limiter
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
import asyncio
from fastapi import BackgroundTasks
from app.core.email import send_email_async

import json as _json
import logging as _logging

_logger = _logging.getLogger(__name__)

router = APIRouter()


def _build_reg_obj(data: dict):
    """Build a simple attribute object from a dict for use with document generators."""
    class _Obj:
        pass
    obj = _Obj()
    for k, v in data.items():
        setattr(obj, k, v)
    return obj


def _build_course_obj(course_dict: dict | None):
    """Build a course-like object (with optional logistics) from a dict."""
    if not course_dict:
        return None

    class _Obj:
        pass

    course_obj = _Obj()
    for k, v in course_dict.items():
        setattr(course_obj, k, v)

    if course_dict.get('logistics'):
        logistics_obj = _Obj()
        for k, v in course_dict['logistics'].items():
            setattr(logistics_obj, k, v)
        course_obj.logistics = logistics_obj
    else:
        course_obj.logistics = None

    return course_obj


def _member_email_html(member_name: str, course_title: str, salutation: str = "") -> str:
    greeting = f"{salutation} {member_name}".strip()
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Welcome to Livecode Technologies!</h2>
            <p>Hello {greeting},</p>
            <p>You have been registered to attend the <strong>{course_title}</strong> training course.</p>
            <p>Attached are your personal training documents. Kindly review them before the session:</p>
            <ul>
                <li>An Invitation Letter</li>
                <li>A Pre-Training Evaluation Form (please fill and return before the course date)</li>
            </ul>
            <p>For queries, feel free to contact us:</p>
            <p><strong>Email:</strong> info@livecodetechnologies.com<br>
            <strong>Tel:</strong> +254 796 190 682</p>
        </div>
    </body>
    </html>
    """


def _lead_email_html(reg_obj, member_count: int = 0) -> str:
    group_note = ""
    if member_count > 0:
        group_note = f"<p>Individual confirmation emails with personal documents have also been sent to each of the <strong>{member_count}</strong> group member(s) you registered.</p>"
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Thank You For Choosing Livecode Technologies!</h2>
            <p>Hello {reg_obj.title or ''} {reg_obj.first_name} {reg_obj.last_name},</p>
            <p>Thank you for registering for the <strong>{reg_obj.course_title}</strong> course. This is to confirm that we have received your registration.</p>
            {group_note}
            <p>Kindly check your attachments for:</p>
            <ul>
                <li>A Payment Invoice</li>
                <li>An Invitation Letter</li>
                <li>A Pre-Training Evaluation Form</li>
            </ul>
            <p>One of our agents will be in touch with you shortly. For queries or requests for assistance, feel free to contact us via:</p>
            <p><strong>Email:</strong> info@livecodetechnologies.com<br>
            <strong>Tel:</strong> +254 796 190 682</p>
        </div>
    </body>
    </html>
    """


async def process_registration_email(registration_dict: dict, course_dict: dict = None):
    """
    Background task that:
    1. Parses group members (if any).
    2. Generates ONE shared invoice (with all participant names) and personal docs for lead.
    3. Sends the lead registrant all 3 documents.
    4. For each group member, generates personal Invitation Letter + Evaluation Form
       and sends them all 3 documents (reusing the shared invoice PDF).
    5. Sends a company notification email with a registration summary.
    """
    from app.core.config import settings as _settings

    reg_obj = _build_reg_obj(registration_dict)
    course_obj = _build_course_obj(course_dict)

    # --- Parse group members ---
    group_members: list[dict] = []
    raw_members = registration_dict.get("group_members_json")
    if raw_members:
        try:
            group_members = _json.loads(raw_members)
        except (_json.JSONDecodeError, TypeError):
            _logger.warning(
                "Could not parse group_members_json for registration %s",
                registration_dict.get("id"),
            )

    # Filter out the lead registrant (billing contact) from group_members if they were included
    # (matching case-insensitively by email) to prevent duplication in invoices and emails.
    lead_email = (reg_obj.email or "").strip().lower()
    group_members = [
        m for m in group_members
        if (m.get("email") or "").strip().lower() != lead_email
    ]

    # --- Generate shared invoice (includes all participant names for group regs) ---
    invoice_buffer = await asyncio.to_thread(
        generate_invoice_pdf, reg_obj, course_obj, group_members or None, reg_obj.currency
    )
    invoice_bytes = invoice_buffer.getvalue()
    invoice_filename = f"Invoice_INV-{str(reg_obj.id)[:8].upper()}.pdf"

    shared_invoice_attachment = {
        "filename": invoice_filename,
        "content": invoice_bytes,
        "maintype": "application",
        "subtype": "pdf",
    }

    def _build_doc_attachments(invitation_buf, form_buf) -> list[dict]:
        """Return the 3 standard attachment dicts, sharing the one invoice."""
        return [
            shared_invoice_attachment,
            {
                "filename": "Invitation_Letter.pdf",
                "content": invitation_buf.getvalue(),
                "maintype": "application",
                "subtype": "pdf",
            },
            {
                "filename": "Pre-Training_Evaluation_Form.docx",
                "content": form_buf.getvalue(),
                "maintype": "application",
                "subtype": "vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        ]

    # --- Generate & send lead registrant email ---
    lead_invitation = await asyncio.to_thread(generate_invitation_letter_pdf, reg_obj, course_obj)
    lead_form = await asyncio.to_thread(generate_pre_training_form_docx, reg_obj, course_obj)

    subject = f"Registration Confirmation – {reg_obj.course_title}"
    await send_email_async(
        reg_obj.email,
        subject,
        _lead_email_html(reg_obj, member_count=len(group_members)),
        _build_doc_attachments(lead_invitation, lead_form),
    )
    _logger.info("Sent lead email to %s", reg_obj.email)

    # --- Send all 3 docs individually to each group member ---
    for member in group_members:
        member_email = member.get("email")
        if not member_email:
            continue

        member_reg_dict = {**registration_dict}
        member_reg_dict["first_name"] = member.get("first_name", "")
        member_reg_dict["last_name"] = member.get("last_name", "")
        member_reg_dict["title"] = member.get("title", "")
        member_reg_dict["phone"] = member.get("phone", "")
        member_reg_dict["email"] = member_email
        member_reg_dict["registration_type"] = "individual"
        member_reg_dict["group_size"] = None
        member_reg_dict["group_members_json"] = None

        member_obj = _build_reg_obj(member_reg_dict)
        member_invitation = await asyncio.to_thread(generate_invitation_letter_pdf, member_obj, course_obj)
        member_form = await asyncio.to_thread(generate_pre_training_form_docx, member_obj, course_obj)

        member_name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip()
        member_subject = f"Training Registration – {reg_obj.course_title}"
        await send_email_async(
            member_email,
            member_subject,
            _member_email_html(member_name, reg_obj.course_title, salutation=member.get("title", "")),
            _build_doc_attachments(member_invitation, member_form),
        )
        _logger.info("Sent member email to %s", member_email)

    # --- Company notification email ---
    company_email = _settings.COMPANY_NOTIFICATION_EMAIL
    if company_email:
        total_participants = 1 + len(group_members)
        reg_type = registration_dict.get("registration_type", "individual")
        member_rows = "".join(
            f"<tr><td style='padding:4px 8px'>{m.get('first_name','')} {m.get('last_name','')}</td>"
            f"<td style='padding:4px 8px'>{m.get('email','')}</td></tr>"
            for m in group_members
        )
        group_section = (
            f"<h4 style='margin-top:16px'>Group Members</h4>"
            f"<table border='1' cellpadding='0' cellspacing='0' style='border-collapse:collapse;font-size:13px'>"
            f"<tr style='background:#0F2942;color:white'><th style='padding:5px 10px'>Name</th><th style='padding:5px 10px'>Email</th></tr>"
            f"{member_rows}</table>"
        ) if group_members else ""

        company_html = f"""
        <html><body style="font-family:Arial,sans-serif;color:#333;padding:20px">
          <h2 style="color:#0F2942">📋 New Course Registration</h2>
          <table style="font-size:14px;border-collapse:collapse;width:100%;max-width:600px">
            <tr><td style="padding:5px 10px"><b>Course:</b></td><td style="padding:5px 10px">{reg_obj.course_title}</td></tr>
            <tr style="background:#F7FAFC"><td style="padding:5px 10px"><b>Type:</b></td><td style="padding:5px 10px">{reg_type.title()} ({total_participants} participant(s))</td></tr>
            <tr><td style="padding:5px 10px"><b>Lead Registrant:</b></td><td style="padding:5px 10px">{(reg_obj.title or '').strip()} {reg_obj.first_name} {reg_obj.last_name}</td></tr>
            <tr style="background:#F7FAFC"><td style="padding:5px 10px"><b>Organisation:</b></td><td style="padding:5px 10px">{registration_dict.get('organization') or 'N/A'}</td></tr>
            <tr><td style="padding:5px 10px"><b>Country:</b></td><td style="padding:5px 10px">{registration_dict.get('country') or 'N/A'}</td></tr>
            <tr style="background:#F7FAFC"><td style="padding:5px 10px"><b>Email:</b></td><td style="padding:5px 10px">{reg_obj.email}</td></tr>
            <tr><td style="padding:5px 10px"><b>Phone:</b></td><td style="padding:5px 10px">{registration_dict.get('phone') or 'N/A'}</td></tr>
            <tr style="background:#F7FAFC"><td style="padding:5px 10px"><b>Schedule:</b></td><td style="padding:5px 10px">{registration_dict.get('schedule_date') or 'N/A'} – {registration_dict.get('schedule_location') or 'N/A'}</td></tr>
          </table>
          {group_section}
          <p style="color:#999;font-size:12px;margin-top:24px">Automated notification · Livecode Technologies registration system</p>
        </body></html>
        """
        notify_subject = f"[New Registration] {reg_obj.course_title} – {reg_obj.first_name} {reg_obj.last_name}"
        await send_email_async(company_email, notify_subject, company_html, [shared_invoice_attachment])
        _logger.info("Sent company notification to %s", company_email)



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

        CREATE TABLE IF NOT EXISTS payment_transaction (
            id UUID NOT NULL PRIMARY KEY,
            registration_id UUID NOT NULL,
            checkout_request_id VARCHAR NOT NULL UNIQUE,
            merchant_request_id VARCHAR,
            amount DOUBLE PRECISION NOT NULL,
            phone_number VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'pending',
            mpesa_receipt_number VARCHAR,
            result_code VARCHAR,
            result_desc VARCHAR,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE,
            FOREIGN KEY(registration_id) REFERENCES course_registration (id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_payment_transaction_registration_id ON payment_transaction (registration_id);
        CREATE INDEX IF NOT EXISTS ix_payment_transaction_checkout_request_id ON payment_transaction (checkout_request_id);
        ''')
        await db.execute(sql)
        await db.commit()
        
        # Also fix the alembic version
        try:
            await db.execute(sa.text("UPDATE alembic_version SET version_num = '9e49804f78bb'"))
            await db.commit()
        except Exception:
            pass
            
        return {"message": "course_registration and payment_transaction tables created successfully! You can now submit registrations."}
    except Exception as e:
        await db.rollback()
        return {"error": str(e)}


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
    # Validate that the course actually exists before attempting insertion
    course_dict = None
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
                }
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

    background_tasks.add_task(process_registration_email, reg_dict, course_dict)

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
    currency: str = "USD",
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
        
    pdf_buffer = generate_invoice_pdf(registration, course, currency=currency)
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

