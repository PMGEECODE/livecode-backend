"""
Secure media-serving endpoint for uploaded course images.

- No directory listing possible (targeted file access only).
- Slug and filename are validated with strict regex before any filesystem access.
- A realpath guard prevents directory-traversal even if validation were bypassed.
- Returns a generic 404 for *any* path that is invalid or does not exist,
  deliberately revealing no information about whether the failure was due to
  path validation, traversal detection, or a missing file.
"""
import os
import re

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from app.core.upload_security import upload_root

router = APIRouter()

# ── Compile validators once at import time ────────────────────────────────────

# Slug: lowercase alphanumeric and hyphens only (mirrors upload.py sanitisation)
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,127}$")

# Filename: UUID (hex + hyphens) followed by an allowed image extension
_FILENAME_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"\.(jpg|jpeg|png|webp|gif)$",
    re.IGNORECASE,
)

_UPLOADS_ROOT = upload_root()

_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.get("/uploads/{slug}/{filename}", include_in_schema=False)
async def serve_course_image(slug: str, filename: str) -> FileResponse:
    """Serve a course upload image with strict path validation."""

    # 1. Validate slug format.
    if not _SLUG_RE.match(slug):
        raise _NOT_FOUND

    # 2. Validate filename format (UUID + allowed extension).
    if not _FILENAME_RE.match(filename):
        raise _NOT_FOUND

    # 3. Construct and canonicalise the target path.
    candidate = os.path.realpath(os.path.join(_UPLOADS_ROOT, slug, filename))

    # 4. Realpath guard — the resolved path MUST be inside _UPLOADS_ROOT.
    if not candidate.startswith(_UPLOADS_ROOT + os.sep):
        raise _NOT_FOUND

    # 5. File must exist and be a regular file.
    if not os.path.isfile(candidate):
        raise _NOT_FOUND

    # 6. Determine MIME type from extension.
    ext = os.path.splitext(filename)[1].lower()
    media_type = _MIME_MAP.get(ext, "application/octet-stream")

    return FileResponse(
        path=candidate,
        media_type=media_type,
        headers={
            # Public images; 1-year browser cache, 1-year CDN cache (Immutable UUIDs).
            "Cache-Control": "public, max-age=31536000, s-maxage=31536000, immutable",
            # Prevent MIME-sniffing attacks.
            "X-Content-Type-Options": "nosniff",
        },
    )
