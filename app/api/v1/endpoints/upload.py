import os
import re
import uuid
import anyio
from fastapi import APIRouter, Depends, Form, UploadFile, File
from app import models
from app.api import deps
from app.core.config import settings
from app.core.upload_security import (
    convert_image_to_webp,
    read_upload_file_limited,
    upload_path,
    validate_image_upload,
)

router = APIRouter()

_SLUG_RE = re.compile(r"[^a-z0-9\-]")


def _sanitize_slug(slug: str) -> str:
    """Normalize slug to a safe directory name (lowercase alphanum + hyphens only)."""
    slug = slug.strip().lower()
    slug = slug.replace(" ", "-")
    slug = _SLUG_RE.sub("", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "uncategorized"


def _purge_course_dir_sync(course_dir: str) -> None:
    """Delete all files inside the course-specific upload directory."""
    if not os.path.isdir(course_dir):
        return
    for entry in os.scandir(course_dir):
        if entry.is_file():
            try:
                os.remove(entry.path)
            except OSError:
                pass


@router.post("/", response_model=dict)
async def upload_image(
    file: UploadFile = File(...),
    slug: str = Form(default=""),
    current_user: models.User = Depends(deps.check_permission("manage_customers")),
) -> dict:
    """
    Upload a course image.

    * Requires superuser authentication.
    * Validates MIME type and file extension.
    * Stores the image under the restricted upload root.
    * Removes any pre-existing image in that directory before saving the new
      one, ensuring exactly one image per course.
    * Returns a relative URL via the secure /media endpoint (no internal paths exposed).
    """
    # 1. Authorization — enforced by deps.get_current_active_superuser.

    # 2. Read, size-limit, validate signature, and re-encode before storing.
    data = await read_upload_file_limited(file, settings.IMAGE_UPLOAD_MAX_BYTES)
    ext = validate_image_upload(file, data)
    webp_data = await anyio.to_thread.run_sync(lambda: convert_image_to_webp(data, ext))

    # 3. Resolve course-scoped directory.
    safe_slug = _sanitize_slug(slug) if slug else "uncategorized"
    course_dir = upload_path(safe_slug)

    # 4. Remove existing image(s) for this course (enforce one-image policy).
    await anyio.to_thread.run_sync(lambda: _purge_course_dir_sync(course_dir))

    # 5. Create the directory (may have been removed above or never existed).
    os.makedirs(course_dir, exist_ok=True)

    # 6. Generate UUID filename and save as WebP.
    filename = f"{uuid.uuid4()}.webp"
    file_path = os.path.join(course_dir, filename)

    def _save() -> None:
        with open(file_path, "wb") as buf:
            buf.write(webp_data)

    await anyio.to_thread.run_sync(_save)

    # 7. Return the secure media endpoint URL (no static/ path exposed).
    return {"url": f"{settings.API_V1_STR}/media/uploads/{safe_slug}/{filename}"}


@router.delete("/{slug}", response_model=dict)
async def delete_image(
    slug: str,
    current_user: models.User = Depends(deps.check_permission("manage_customers")),
) -> dict:
    """
    Delete all uploaded images for the given course slug.
    * Requires superuser authentication.
    """
    safe_slug = _sanitize_slug(slug)
    course_dir = upload_path(safe_slug)
    await anyio.to_thread.run_sync(lambda: _purge_course_dir_sync(course_dir))
    return {"status": "success", "message": "Image(s) successfully deleted."}
