"""
Tests for the secure media endpoint (app/api/v1/endpoints/media.py).

Covers:
- Valid slug + existing file → 200 with correct Content-Type
- Valid slug + missing file → 404
- Invalid slug (path traversal, bad chars) → 404
- Invalid filename (path traversal, bad chars, wrong extension) → 404
- Legacy /static/uploads/ redirect → 301 to new endpoint
"""
import os
import shutil
import uuid
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from fastapi import status
from app.main import app

# ── Test fixtures ─────────────────────────────────────────────────────────────

_TEST_SLUG = "test-media-course"
_TEST_UUID = str(uuid.uuid4())
_TEST_FILE = f"{_TEST_UUID}.png"
_UPLOAD_DIR = os.path.join("static", "uploads", _TEST_SLUG)
_TEST_FILE_PATH = os.path.join(_UPLOAD_DIR, _TEST_FILE)


@pytest_asyncio.fixture(autouse=True)
async def setup_test_file():
    """Create a real file in static/uploads so the endpoint can serve it."""
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    with open(_TEST_FILE_PATH, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)  # minimal PNG header bytes
    yield
    shutil.rmtree(_UPLOAD_DIR, ignore_errors=True)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Helper ────────────────────────────────────────────────────────────────────

def _media_url(slug: str, filename: str) -> str:
    return f"/api/v1/media/uploads/{slug}/{filename}"


# ── A) Happy-path tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_media_serves_existing_file(client: AsyncClient):
    """Valid slug + UUID filename pointing to an existing file → 200."""
    resp = await client.get(_media_url(_TEST_SLUG, _TEST_FILE))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers["content-type"].startswith("image/png")


@pytest.mark.asyncio
async def test_media_sets_cache_control_header(client: AsyncClient):
    """Served images must carry a public Cache-Control header."""
    resp = await client.get(_media_url(_TEST_SLUG, _TEST_FILE))
    assert resp.status_code == status.HTTP_200_OK
    cc = resp.headers.get("cache-control", "")
    assert "public" in cc


@pytest.mark.asyncio
async def test_media_sets_nosniff_header(client: AsyncClient):
    """Served images must carry X-Content-Type-Options: nosniff."""
    resp = await client.get(_media_url(_TEST_SLUG, _TEST_FILE))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers.get("x-content-type-options") == "nosniff"


# ── B) Missing file ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_media_missing_file_returns_404(client: AsyncClient):
    """Valid slug + well-formed filename but file doesn't exist → 404."""
    missing = f"{uuid.uuid4()}.png"
    resp = await client.get(_media_url(_TEST_SLUG, missing))
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# ── C) Slug validation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_media_rejects_slug_with_path_traversal(client: AsyncClient):
    """Slug containing '../' must be rejected."""
    resp = await client.get(_media_url("../etc/passwd", _TEST_FILE))
    # FastAPI will 404 (path param) or our guard fires — either way not 200.
    assert resp.status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


@pytest.mark.asyncio
async def test_media_rejects_slug_with_uppercase(client: AsyncClient):
    """Slug with uppercase letters fails our regex → 404."""
    resp = await client.get(_media_url("INVALID-SLUG", _TEST_FILE))
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_media_rejects_slug_starting_with_hyphen(client: AsyncClient):
    """Slug starting with a hyphen fails our regex → 404."""
    resp = await client.get(_media_url("-bad-slug", _TEST_FILE))
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# ── D) Filename validation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_media_rejects_filename_without_uuid_format(client: AsyncClient):
    """Filename that is not a UUID → 404."""
    resp = await client.get(_media_url(_TEST_SLUG, "not-a-uuid.png"))
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_media_rejects_disallowed_extension(client: AsyncClient):
    """Filename with a disallowed extension (e.g. .exe) → 404."""
    bad_name = f"{uuid.uuid4()}.exe"
    resp = await client.get(_media_url(_TEST_SLUG, bad_name))
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_media_rejects_filename_with_path_traversal(client: AsyncClient):
    """Filename with '../' in it must not reach the filesystem."""
    resp = await client.get(_media_url(_TEST_SLUG, f"../{_TEST_SLUG}/{_TEST_FILE}"))
    assert resp.status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


@pytest.mark.asyncio
async def test_media_rejects_null_byte_in_filename(client: AsyncClient):
    """Null bytes in filename must not reach the filesystem."""
    bad = f"{uuid.uuid4()}\x00.png"
    resp = await client.get(_media_url(_TEST_SLUG, bad))
    assert resp.status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        status.HTTP_400_BAD_REQUEST,
    )


# ── E) Legacy redirect ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_legacy_static_redirect(client: AsyncClient):
    """GET /static/uploads/{slug}/{filename} must redirect (301) to /api/v1/media/uploads/..."""
    resp = await client.get(
        f"/static/uploads/{_TEST_SLUG}/{_TEST_FILE}",
        follow_redirects=False,
    )
    assert resp.status_code == status.HTTP_301_MOVED_PERMANENTLY
    location = resp.headers.get("location", "")
    assert f"/api/v1/media/uploads/{_TEST_SLUG}/{_TEST_FILE}" in location


@pytest.mark.asyncio
async def test_legacy_redirect_followed_serves_file(client: AsyncClient):
    """Following the legacy redirect must ultimately serve the file."""
    resp = await client.get(
        f"/static/uploads/{_TEST_SLUG}/{_TEST_FILE}",
        follow_redirects=True,
    )
    assert resp.status_code == status.HTTP_200_OK
