import os
import re
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
from app.core.upload_security import (
    convert_image_to_webp,
    read_upload_file_limited,
    upload_path,
    validate_image_upload,
)

router = APIRouter()

_SAFE_RE = re.compile(r"[^a-z0-9\-]")

os.makedirs(upload_path("partners"), exist_ok=True)


def _sanitize_name(name: str) -> str:
    slug = name.strip().lower().replace(" ", "-")
    slug = _SAFE_RE.sub("", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "partner"


from app.core.redis import redis_manager
from fastapi.encoders import jsonable_encoder
import json

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
    cache_key = "partners:list:active"
    
    # 1. Try Redis Cache
    cached_data = await redis_manager.get(cache_key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except Exception:
            pass
            
    # 2. Fetch from DB
    partners = await trusted_partner.get_all_active(db)
    
    # 3. Save to Redis Cache (1 hour)
    if partners:
        await redis_manager.set(cache_key, json.dumps(jsonable_encoder(partners)), expire=3600)
        
    return partners


# ──────────────────────────────────────────────
# Admin endpoints — superuser only
# ──────────────────────────────────────────────

@router.get("/admin", response_model=List[TrustedPartner])
async def list_all_partners(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("view_performance_metrics")),
) -> Any:
    """Return all trusted partners (including inactive) for admin management."""
    return await trusted_partner.get_all(db)


@router.post("/", response_model=TrustedPartner, status_code=status.HTTP_201_CREATED)
async def create_partner(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("manage_customers")),
    partner_in: TrustedPartnerCreate,
) -> Any:
    """Create a new trusted partner."""
    obj = await trusted_partner.create(db, obj_in=partner_in)
    await redis_manager.delete("partners:list:active")
    return obj


@router.put("/{partner_id}", response_model=TrustedPartner)
async def update_partner(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("manage_customers")),
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
    
    obj = await trusted_partner.update(db, db_obj=db_obj, obj_in=partner_in)
    await redis_manager.delete("partners:list:active")
    return obj


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("manage_customers")),
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
        filename = db_obj.logo_url.rsplit("/", 1)[-1]
        file_path = upload_path("partners", filename)

        def _remove() -> None:
            if os.path.isfile(file_path):
                os.remove(file_path)

        await anyio.to_thread.run_sync(_remove)

    await trusted_partner.remove(db, id=uid)
    await redis_manager.delete("partners:list:active")


@router.post("/upload-logo", response_model=dict)
async def upload_partner_logo(
    file: UploadFile = File(...),
    partner_name: str = Form(default=""),
    current_user: models.User = Depends(deps.check_permission("manage_customers")),
) -> dict:
    """
    Upload a partner logo image.
    - Validates MIME type and extension.
    - Compresses and converts raster images to lossless WebP via FFmpeg.
    - Returns a relative URL via the /media endpoint.
    """
    data = await read_upload_file_limited(file, settings.IMAGE_UPLOAD_MAX_BYTES)
    ext = validate_image_upload(file, data)
    webp_data = await anyio.to_thread.run_sync(lambda: convert_image_to_webp(data, ext))

    saved_filename = f"{uuid.uuid4()}.webp"
    file_path = upload_path("partners", saved_filename)

    def _save() -> None:
        with open(file_path, "wb") as buf:
            buf.write(webp_data)

    await anyio.to_thread.run_sync(_save)

    return {"url": f"{settings.API_V1_STR}/media/uploads/partners/{saved_filename}"}
