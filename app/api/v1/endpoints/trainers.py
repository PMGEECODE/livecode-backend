import os
import re
import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
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
from app.core.upload_security import (
    read_upload_file_limited,
    scan_bytes_for_malware,
    upload_path,
    validate_document_upload,
)

router = APIRouter()

ALLOWED_DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".rtf", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

TRAINER_UPLOAD_DIR = upload_path("trainers")
os.makedirs(TRAINER_UPLOAD_DIR, exist_ok=True)

# Compile filename validator
_FILENAME_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"\.(pdf|doc|docx|rtf|txt)$",
    re.IGNORECASE,
)

_UPLOADS_ROOT = os.path.realpath(TRAINER_UPLOAD_DIR)


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
    - Saves document securely to prevent directory traversal or unauthenticated listing.
    """
    data = await read_upload_file_limited(file, MAX_FILE_SIZE)
    ext = validate_document_upload(file, data, ALLOWED_DOC_EXTENSIONS)
    await anyio.to_thread.run_sync(lambda: scan_bytes_for_malware(data))

    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(TRAINER_UPLOAD_DIR, filename)

    def _save() -> None:
        with open(file_path, "wb") as buf:
            buf.write(data)

    await anyio.to_thread.run_sync(_save)

    return {"filename": filename}


@router.post("/apply", response_model=TrainerApplicationResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def submit_trainer_application(
    request: Request,
    response: Response,
    application_in: TrainerApplicationCreate,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Public application submission endpoint.
    - Validates inputs strictly.
    - Verifies the uploaded CV file exists locally.
    """
    # 1. Verify CV file exists
    cv_filename = application_in.cv_url
    if not _FILENAME_RE.match(cv_filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid CV filename format.",
        )
    cv_path = os.path.realpath(os.path.join(_UPLOADS_ROOT, cv_filename))
    if not cv_path.startswith(_UPLOADS_ROOT + os.sep):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    if not os.path.isfile(cv_path):
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
        cl_path = os.path.realpath(os.path.join(_UPLOADS_ROOT, cl_filename))
        if not cl_path.startswith(_UPLOADS_ROOT + os.sep):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        if not os.path.isfile(cl_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded Cover Letter document was not found or has expired.",
            )

    # 3. Create database entry
    return await trainer_application.create(db, obj_in=application_in)


# ──────────────────────────────────────────────
# Admin/Superuser Endpoints
# ──────────────────────────────────────────────

@router.get("/applications", response_model=List[TrainerApplicationResponse])
async def list_trainer_applications(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve trainer applications. (Admin-only)
    """
    return await trainer_application.get_multi_by_status(db, status=status, skip=skip, limit=limit)


@router.put("/applications/{app_id}/status", response_model=TrainerApplicationResponse)
async def update_application_status(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
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

    return await trainer_application.update(db, db_obj=db_obj, obj_in=status_in)


@router.get("/applications/{app_id}/cv")
async def download_trainer_cv(
    app_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> FileResponse:
    """
    Secure CV document retrieval.
    - Prevents directory traversal with a realpath guard.
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

    candidate = os.path.realpath(os.path.join(_UPLOADS_ROOT, filename))
    if not candidate.startswith(_UPLOADS_ROOT + os.sep):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    if not os.path.isfile(candidate):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CV document file does not exist on disk.",
        )

    return FileResponse(
        path=candidate,
        media_type="application/octet-stream",
        filename=f"{db_obj.full_name.replace(' ', '_')}_CV{os.path.splitext(filename)[1]}",
        headers={
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/applications/{app_id}/cover-letter")
async def download_trainer_cover_letter(
    app_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> FileResponse:
    """
    Secure Cover Letter retrieval.
    - Prevents directory traversal.
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

    candidate = os.path.realpath(os.path.join(_UPLOADS_ROOT, filename))
    if not candidate.startswith(_UPLOADS_ROOT + os.sep):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    if not os.path.isfile(candidate):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover letter document file does not exist on disk.",
        )

    return FileResponse(
        path=candidate,
        media_type="application/octet-stream",
        filename=f"{db_obj.full_name.replace(' ', '_')}_CoverLetter{os.path.splitext(filename)[1]}",
        headers={
            "X-Content-Type-Options": "nosniff",
        },
    )
