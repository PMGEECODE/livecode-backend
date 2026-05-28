import os
import re
import shutil
import uuid
from typing import Any, List
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
import anyio

from app import models, schemas
from app.api import deps
from app.crud.partner import trusted_partner
from app.schemas.partner import TrustedPartner, TrustedPartnerCreate, TrustedPartnerUpdate
from app.core.config import settings
from app.core.limiter import limiter

router = APIRouter()

PARTNER_UPLOAD_DIR = "static/uploads/partners"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
_SAFE_RE = re.compile(r"[^a-z0-9\-]")

os.makedirs(PARTNER_UPLOAD_DIR, exist_ok=True)


def _sanitize_name(name: str) -> str:
    slug = name.strip().lower().replace(" ", "-")
    slug = _SAFE_RE.sub("", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "partner"


# ──────────────────────────────────────────────
# Public endpoint — no auth required
# ──────────────────────────────────────────────

@router.get("/", response_model=List[TrustedPartner])
@limiter.limit("60/minute")
async def list_active_partners(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """Return all active trusted partners ordered by display_order."""
    return await trusted_partner.get_all_active(db)


# ──────────────────────────────────────────────
# Admin endpoints — superuser only
# ──────────────────────────────────────────────

@router.get("/admin", response_model=List[TrustedPartner])
async def list_all_partners(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Return all trusted partners (including inactive) for admin management."""
    return await trusted_partner.get_all(db)


@router.post("/", response_model=TrustedPartner, status_code=status.HTTP_201_CREATED)
async def create_partner(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
    partner_in: TrustedPartnerCreate,
) -> Any:
    """Create a new trusted partner."""
    return await trusted_partner.create(db, obj_in=partner_in)


@router.put("/{partner_id}", response_model=TrustedPartner)
async def update_partner(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
    partner_id: str,
    partner_in: TrustedPartnerUpdate,
) -> Any:
    """Update a trusted partner."""
    try:
        import uuid as _uuid
        uid = _uuid.UUID(partner_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid partner ID.")

    db_obj = await trusted_partner.get(db, id=uid)
    if not db_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found.")
    return await trusted_partner.update(db, db_obj=db_obj, obj_in=partner_in)


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
    partner_id: str,
) -> None:
    """Permanently delete a trusted partner and its logo file."""
    try:
        import uuid as _uuid
        uid = _uuid.UUID(partner_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid partner ID.")

    db_obj = await trusted_partner.get(db, id=uid)
    if not db_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found.")

    # Attempt to remove the stored logo file
    if db_obj.logo_url:
        # logo_url is like /api/v1/media/uploads/partners/<filename>
        # Derive the local filesystem path
        relative = db_obj.logo_url.replace(f"{settings.API_V1_STR}/media/", "", 1)
        file_path = os.path.join("static", relative)

        def _remove() -> None:
            if os.path.isfile(file_path):
                os.remove(file_path)

        await anyio.to_thread.run_sync(_remove)

    await trusted_partner.remove(db, id=uid)


@router.post("/upload-logo", response_model=dict)
async def upload_partner_logo(
    file: UploadFile = File(...),
    partner_name: str = Form(default=""),
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> dict:
    """
    Upload a partner logo image.
    - Validates MIME type and extension.
    - Stores under static/uploads/partners/.
    - Returns a relative URL via the /media endpoint.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files are allowed.",
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image format. Allowed: jpg, jpeg, png, webp, gif, svg.",
        )

    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(PARTNER_UPLOAD_DIR, filename)

    def _save() -> None:
        with open(file_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

    await anyio.to_thread.run_sync(_save)

    return {"url": f"{settings.API_V1_STR}/media/uploads/partners/{filename}"}
