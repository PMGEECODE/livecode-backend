import os
import re
import uuid
from html import escape
from typing import Any, List, Optional
from urllib.parse import quote
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
import anyio

from app import models, schemas
from app.api import deps
from app.crud.trainer import trainer_application
from app.schemas.trainer import (
    TrainerApplicationResponse,
    TrainerApplicationCreate,
    TrainerApplicationUpdate,
)
from app.core.limiter import limiter
from app.core.config import settings
from app.core.email import send_email_async
from app.core.upload_security import (
    read_upload_file_limited,
    scan_bytes_for_malware,
    validate_document_upload,
)
from app.services.s3_storage import (
    download_private_object,
    object_exists,
    trainer_object_key,
    upload_private_object,
)

router = APIRouter()

ALLOWED_DOC_EXTENSIONS = {".pdf", ".doc", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Compile filename validator
_FILENAME_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"\.(pdf|doc|docx)$",
    re.IGNORECASE,
)
_DOCUMENT_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe_download_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value[:80] or "trainer_application"


def _html_value(value: Optional[str]) -> str:
    return escape(value or "Not provided")


def _content_disposition(filename: str) -> str:
    quoted = quote(filename)
    return f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quoted}"


async def _trainer_document_exists(filename: str) -> bool:
    return await anyio.to_thread.run_sync(lambda: object_exists(trainer_object_key(filename)))


async def _download_trainer_document(filename: str):
    return await anyio.to_thread.run_sync(lambda: download_private_object(trainer_object_key(filename)))


def _trainer_notification_html(application: TrainerApplicationResponse) -> str:
    admin_hint = "Please sign in to the LiveCode admin dashboard to review CV and cover letter documents."
    rows = [
        ("Full name", application.full_name),
        ("Email", str(application.email)),
        ("Phone", application.phone),
        ("Alternate phone", application.alternate_phone),
        ("Date of birth", application.dob),
        ("Gender", application.gender),
        ("Location", f"{application.city}, {application.country}"),
        ("Specialization", application.specialization),
        ("Other specialization", application.other_specialization),
        ("CV uploaded", "Yes"),
        ("Cover letter uploaded", "Yes" if application.cover_letter_url else "No"),
    ]

    referee_rows = []
    for idx in (1, 2, 3):
        name = getattr(application, f"referee{idx}_name")
        if not name:
            continue
        referee_rows.append(
            f"""
            <tr>
              <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-weight:700;color:#001A4D;">Referee {idx}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#334155;">
                {_html_value(name)}<br>
                <span style="color:#64748b;">{_html_value(getattr(application, f"referee{idx}_speciality"))}</span><br>
                {_html_value(getattr(application, f"referee{idx}_phone"))}<br>
                {_html_value(str(getattr(application, f"referee{idx}_email") or ""))}
              </td>
            </tr>
            """
        )

    detail_rows = "".join(
        f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-weight:700;color:#001A4D;width:34%;">{escape(label)}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#334155;">{_html_value(value)}</td>
        </tr>
        """
        for label, value in rows
    )

    return f"""
    <div style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
      <div style="max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
        <div style="background:#001A4D;color:#ffffff;padding:22px 24px;">
          <h1 style="margin:0;color:#F49220;font-size:22px;">New Trainer Application</h1>
          <p style="margin:8px 0 0;color:#dbeafe;font-size:14px;">A new trainer application was submitted through the website.</p>
        </div>
        <div style="padding:24px;">
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            {detail_rows}
            {''.join(referee_rows)}
          </table>
          <p style="margin:20px 0 0;padding:14px 16px;background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;color:#9a3412;font-size:13px;line-height:1.5;">
            {escape(admin_hint)}
          </p>
        </div>
      </div>
    </div>
    """


async def notify_company_about_trainer_application(application: TrainerApplicationResponse) -> None:
    if not settings.COMPANY_NOTIFICATION_EMAIL:
        return
    await send_email_async(
        settings.COMPANY_NOTIFICATION_EMAIL,
        f"New Trainer Application: {application.full_name}",
        _trainer_notification_html(application),
    )


# ──────────────────────────────────────────────
# Public Endpoints
# ──────────────────────────────────────────────

@router.post("/upload-document", response_model=dict)
@limiter.limit("10/minute")
async def upload_trainer_document(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
) -> dict:
    """
    Public upload endpoint for trainer CVs and Cover Letters.
    - Validates file type and size.
    - Scans before upload.
    - Stores document in private S3-compatible storage.
    """
    data = await read_upload_file_limited(file, MAX_FILE_SIZE)
    ext = validate_document_upload(file, data, ALLOWED_DOC_EXTENSIONS)
    await anyio.to_thread.run_sync(lambda: scan_bytes_for_malware(data, require_scanner=True))

    filename = f"{uuid.uuid4()}{ext}"
    key = trainer_object_key(filename)
    content_type = _DOCUMENT_CONTENT_TYPES.get(ext, "application/octet-stream")
    await anyio.to_thread.run_sync(
        lambda: upload_private_object(
            key=key,
            data=data,
            content_type=content_type,
            original_filename=file.filename,
        )
    )

    return {"filename": filename}


@router.post("/apply", response_model=TrainerApplicationResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def submit_trainer_application(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    application_in: TrainerApplicationCreate,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Public application submission endpoint.
    - Validates inputs strictly.
    - Verifies the uploaded CV file exists in private S3 storage.
    """
    # 1. Verify CV file exists
    cv_filename = application_in.cv_url
    if not _FILENAME_RE.match(cv_filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid CV filename format.",
        )
    if not await _trainer_document_exists(cv_filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded CV document was not found or has expired. Please re-upload.",
        )

    # 2. Verify Cover Letter file exists if provided
    if application_in.cover_letter_url:
        cl_filename = application_in.cover_letter_url
        if not _FILENAME_RE.match(cl_filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cover letter filename format.",
            )
        if not await _trainer_document_exists(cl_filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded Cover Letter document was not found or has expired.",
            )

    # 3. Create database entry, then notify company in the background
    created = await trainer_application.create(db, obj_in=application_in)
    response_model = TrainerApplicationResponse.model_validate(created)
    background_tasks.add_task(notify_company_about_trainer_application, response_model)
    return created


# ──────────────────────────────────────────────
# Admin/Superuser Endpoints
# ──────────────────────────────────────────────

@router.get("/applications", response_model=List[TrainerApplicationResponse])
async def list_trainer_applications(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("view_trainers")),
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve trainer applications. (Admin-only)
    """
    return await trainer_application.get_multi_by_status(db, status=status, skip=skip, limit=limit)


async def notify_trainer_approval(application: TrainerApplicationResponse) -> None:
    html_body = f"""
    <div style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
      <div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
        <div style="background:#001A4D;color:#ffffff;padding:22px 24px;">
          <h1 style="margin:0;color:#F49220;font-size:22px;">Application Approved</h1>
        </div>
        <div style="padding:24px;color:#334155;line-height:1.6;">
          <p>Dear {escape(application.full_name)},</p>
          <p>Congratulations! Your application to become a trainer at <b>Livecode Technologies Ltd</b> has been <b>approved</b>.</p>
          <p>Our faculty team is excited to welcome you and will reach out to you shortly with next steps, scheduling, and onboarding information.</p>
          <p>We look forward to a successful collaboration.</p>
          <p style="margin-top:20px;">Best regards,<br><b>Management Team</b><br>Livecode Technologies Ltd</p>
        </div>
      </div>
    </div>
    """
    await send_email_async(
        str(application.email),
        "Update: Your Trainer Application is Approved",
        html_body,
    )


async def notify_trainer_rejection(application: TrainerApplicationResponse) -> None:
    from app.core.document_modules.trainer_rejection import generate_trainer_rejection_letter_pdf
    
    html_body = f"""
    <div style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
      <div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
        <div style="background:#001A4D;color:#ffffff;padding:22px 24px;">
          <h1 style="margin:0;color:#F49220;font-size:22px;">Update on Your Application</h1>
        </div>
        <div style="padding:24px;color:#334155;line-height:1.6;">
          <p>Dear {escape(application.full_name)},</p>
          <p>Thank you for your interest in joining Livecode Technologies Ltd as a trainer.</p>
          <p>Please find attached an official letter regarding the status of your application.</p>
          <p style="margin-top:20px;">Best regards,<br><b>Management Team</b><br>Livecode Technologies Ltd</p>
        </div>
      </div>
    </div>
    """
    
    pdf_buffer = await anyio.to_thread.run_sync(
        lambda: generate_trainer_rejection_letter_pdf(application)
    )
    
    attachments = [
        {
            "maintype": "application",
            "subtype": "pdf",
            "filename": "Application_Status_Livecode.pdf",
            "content": pdf_buffer.getvalue(),
        }
    ]
    
    await send_email_async(
        str(application.email),
        "Update: Trainer Application Status",
        html_body,
        attachments=attachments,
    )


@router.put("/applications/{app_id}/status", response_model=TrainerApplicationResponse)
async def update_application_status(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("manage_trainers")),
    background_tasks: BackgroundTasks,
    app_id: str,
    status_in: TrainerApplicationUpdate,
) -> Any:
    """
    Update application status (approve, decline, archive). (Admin-only)
    """
    try:
        uid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid application ID format.",
        )

    db_obj = await trainer_application.get(db, id=uid)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trainer application not found.",
        )

    old_status = db_obj.status
    updated = await trainer_application.update(db, db_obj=db_obj, obj_in=status_in)

    # Trigger emails on status change
    if old_status != updated.status:
        response_model = TrainerApplicationResponse.model_validate(updated)
        if updated.status == "approved":
            background_tasks.add_task(notify_trainer_approval, response_model)
        elif updated.status == "declined":
            background_tasks.add_task(notify_trainer_rejection, response_model)

    return updated


@router.get("/applications/{app_id}/cv")
async def download_trainer_cv(
    app_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("view_trainers")),
) -> Response:
    """
    Secure CV document retrieval.
    - Reads from private S3-compatible storage.
    - Requires active superuser auth context.
    """
    try:
        uid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid application ID format.",
        )

    db_obj = await trainer_application.get(db, id=uid)
    if not db_obj or not db_obj.cv_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application CV not found.",
        )

    filename = db_obj.cv_url
    if not _FILENAME_RE.match(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid CV filename format.",
        )

    stored = await _download_trainer_document(filename)
    download_name = f"{_safe_download_name(db_obj.full_name)}_CV{os.path.splitext(filename)[1]}"
    return Response(
        content=stored.content,
        media_type=stored.content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": _content_disposition(download_name),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/applications/{app_id}/cover-letter")
async def download_trainer_cover_letter(
    app_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("view_trainers")),
) -> Response:
    """
    Secure Cover Letter retrieval.
    - Reads from private S3-compatible storage.
    - Requires superuser auth.
    """
    try:
        uid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid application ID format.",
        )

    db_obj = await trainer_application.get(db, id=uid)
    if not db_obj or not db_obj.cover_letter_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover letter not found for this application.",
        )

    filename = db_obj.cover_letter_url
    if not _FILENAME_RE.match(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document filename format.",
        )

    stored = await _download_trainer_document(filename)
    download_name = f"{_safe_download_name(db_obj.full_name)}_CoverLetter{os.path.splitext(filename)[1]}"
    return Response(
        content=stored.content,
        media_type=stored.content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": _content_disposition(download_name),
            "Cache-Control": "private, no-store",
        },
    )
