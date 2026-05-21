import os
import re
import shutil
import uuid
import anyio
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from app import models
from app.api import deps
from app.core.config import settings

router = APIRouter()

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
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
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> dict:
    """
    Upload a course image.

    * Requires superuser authentication.
    * Validates MIME type and file extension.
    * Stores the image under ``static/uploads/{slug}/``.
    * Removes any pre-existing image in that directory before saving the new
      one, ensuring exactly one image per course.
    * Returns a relative URL via the secure /media endpoint (no internal paths exposed).
    """
    # 1. Authorization — enforced by deps.get_current_active_superuser.

    # 2. MIME type validation.
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files are allowed.",
        )

    # 3. Extension validation.
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image format.",
        )

    # 4. Resolve course-scoped directory.
    safe_slug = _sanitize_slug(slug) if slug else "uncategorized"
    course_dir = os.path.join(UPLOAD_DIR, safe_slug)

    # 5. Remove existing image(s) for this course (enforce one-image policy).
    await anyio.to_thread.run_sync(lambda: _purge_course_dir_sync(course_dir))

    # 6. Create the directory (may have been removed above or never existed).
    os.makedirs(course_dir, exist_ok=True)

    # 7. Generate UUID filename and save asynchronously.
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(course_dir, filename)

    def _save() -> None:
        with open(file_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

    await anyio.to_thread.run_sync(_save)

    # 8. Return the secure media endpoint URL (no static/ path exposed).
    return {"url": f"{settings.API_V1_STR}/media/uploads/{safe_slug}/{filename}"}

