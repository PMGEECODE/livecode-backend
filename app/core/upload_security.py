import os
import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
IMAGE_SIGNATURES = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}


def upload_root() -> str:
    root = settings.UPLOAD_ROOT
    if not os.path.isabs(root):
        root = os.path.join(os.getcwd(), root)
    os.makedirs(root, exist_ok=True)
    return os.path.realpath(root)


def upload_path(*parts: str) -> str:
    root = upload_root()
    candidate = os.path.realpath(os.path.join(root, *parts))
    if candidate != root and not candidate.startswith(root + os.sep):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid upload path.")
    return candidate


async def read_upload_file_limited(file: UploadFile, max_bytes: int) -> bytes:
    data = bytearray()
    while chunk := await file.read(65536):
        data.extend(chunk)
        if len(data) > max_bytes:
            max_mb = max_bytes / (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds the {max_mb:g}MB limit.",
            )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    await file.seek(0)
    return bytes(data)


def validate_image_upload(file: UploadFile, data: bytes) -> str:
    ext = os.path.splitext(file.filename or "")[1].lower()
    is_image_mime = file.content_type and file.content_type.startswith("image/")
    is_image_ext = ext in ALLOWED_IMAGE_EXTENSIONS
    if not (is_image_mime or is_image_ext):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image files are allowed.")

    if ext == ".svg":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SVG uploads are not allowed.")

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image format. Allowed: jpg, jpeg, png, webp, gif.",
        )

    signatures = IMAGE_SIGNATURES[ext]
    if not any(data.startswith(signature) for signature in signatures):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File content does not match the image type.")

    if ext == ".webp":
        if len(data) < 12 or data[8:12] != b"WEBP":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WebP image content.")

    return ext


def validate_document_upload(file: UploadFile, data: bytes, allowed_extensions: set[str]) -> str:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported document format. Allowed formats: PDF, DOC, DOCX.",
        )

    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid PDF document content.")
    if ext == ".doc" and not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid DOC document content.")
    if ext == ".docx" and not data.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid DOCX document content.")
    if ext == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or not any(name.startswith("word/") for name in names):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid DOCX document content.")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid DOCX document content.")

    return ext


def convert_image_to_webp(data: bytes, source_ext: str) -> bytes:
    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    if not os.path.exists(ffmpeg):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image conversion service is not available.",
        )

    temp_in_path = ""
    temp_out_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=source_ext, delete=False) as temp_in:
            temp_in.write(data)
            temp_in_path = temp_in.name

        with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as temp_out:
            temp_out_path = temp_out.name

        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            temp_in_path,
            "-frames:v",
            "1",
            "-vf",
            "scale='min(1600,iw)':-2",
            "-c:v",
            "libwebp",
            "-quality",
            "82",
            "-preset",
            "picture",
            "-an",
            "-y",
            temp_out_path,
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=20)
        converted = Path(temp_out_path).read_bytes()
        if not converted.startswith(b"RIFF") or converted[8:12] != b"WEBP":
            raise ValueError("Converted file is not valid WebP.")
        return converted
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image conversion timed out.")
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded image could not be safely processed.")
    finally:
        for path in (temp_in_path, temp_out_path):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


def scan_bytes_for_malware(data: bytes, *, require_scanner: bool | None = None) -> None:
    scanner_required = settings.REQUIRE_MALWARE_SCANNER if require_scanner is None else require_scanner
    scanner = shutil.which(settings.CLAMSCAN_PATH) or settings.CLAMSCAN_PATH
    if not scanner or not os.path.exists(scanner):
        if scanner_required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Malware scanning service is not available.",
            )
        return

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(data)
            temp_path = temp_file.name

        result = subprocess.run(
            [scanner, "--no-summary", temp_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if result.returncode == 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malware detected in uploaded file.")
        if result.returncode != 0:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Malware scan failed.")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Malware scan timed out.")
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass
