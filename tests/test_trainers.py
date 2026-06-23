import io
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import patch, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.api.deps import get_db, get_current_active_superuser, get_current_active_user
from app.db.base import Base
from app.db.models.user import User
from app.services.s3_storage import StoredObject

# ──────────────────────────────────────────────────────────────
# Test DB setup
# ──────────────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///./tests/test_trainers_db.sqlite"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Initialize and tear down an isolated schema per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


async def mock_superuser():
    return User(
        id=uuid.uuid4(),
        full_name="System Admin",
        email="admin@livecodetech.co.ke",
        hashed_password="hashed_pwd",
        is_active=True,
        is_superuser=True,
    )  # type: ignore


from app.core.config import settings
from app.core.upload_security import upload_root

_MOCK_S3 = {}

@pytest_asyncio.fixture(autouse=True)
def mock_s3_and_malware():
    _MOCK_S3.clear()
    
    def mock_upload_private_object(*, key, data, content_type, original_filename=None):
        _MOCK_S3[key] = StoredObject(
            key=key,
            content=data,
            content_type=content_type,
            content_length=len(data)
        )
        
    def mock_object_exists(key):
        return key in _MOCK_S3
        
    def mock_download_private_object(key):
        if key not in _MOCK_S3:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Document was not found in secure storage.")
        return _MOCK_S3[key]

    with patch("app.api.v1.endpoints.trainers.upload_private_object", side_effect=mock_upload_private_object), \
         patch("app.api.v1.endpoints.trainers.object_exists", side_effect=mock_object_exists), \
         patch("app.api.v1.endpoints.trainers.download_private_object", side_effect=mock_download_private_object), \
         patch("app.api.v1.endpoints.trainers.scan_bytes_for_malware", return_value=None):
        yield


@pytest_asyncio.fixture(autouse=True)
async def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    original_scanner_setting = settings.REQUIRE_MALWARE_SCANNER
    settings.REQUIRE_MALWARE_SCANNER = False
    yield
    settings.REQUIRE_MALWARE_SCANNER = original_scanner_setting
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]
    if get_current_active_superuser in app.dependency_overrides:
        del app.dependency_overrides[get_current_active_superuser]
    if get_current_active_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_active_user]


# Store the uploaded CV filename across tests
_cv_filename: str = ""


# ──────────────────────────────────────────────────────────────
# 1. Document Upload Tests
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_valid_pdf():
    """A PDF file should be accepted and return a safe filename."""
    global _cv_filename
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")
        fake_pdf.name = "cv.pdf"
        resp = await client.post(
            "/api/v1/trainers/upload-document",
            files={"file": ("cv.pdf", fake_pdf, "application/pdf")},
        )
    assert resp.status_code in (200, 201), resp.text
    data = resp.json()
    assert "filename" in data
    assert data["filename"].endswith(".pdf")
    _cv_filename = data["filename"]


@pytest.mark.asyncio
async def test_upload_invalid_extension_rejected():
    """Executable/script uploads must be rejected with HTTP 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fake_exe = io.BytesIO(b"MZ malicious payload")
        resp = await client.post(
            "/api/v1/trainers/upload-document",
            files={"file": ("malware.exe", fake_exe, "application/octet-stream")},
        )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_image_rejected():
    """Image files must be rejected — only document formats are allowed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fake_img = io.BytesIO(b"\x89PNG fake image")
        resp = await client.post(
            "/api/v1/trainers/upload-document",
            files={"file": ("photo.png", fake_img, "image/png")},
        )
    assert resp.status_code == 400


# ──────────────────────────────────────────────────────────────
# 2. Application Submission Tests
# ──────────────────────────────────────────────────────────────

def _valid_payload(cv_filename: str) -> dict:
    return {
        "full_name": "Grace Wanjiru",
        "email": "grace@example.com",
        "phone": "+254700000001",
        "dob": "1990-05-15",
        "gender": "Female",
        "country": "Kenya",
        "city": "Nairobi",
        "specialization": "Data Science, GIS, Remote Sensing",
        "cv_url": cv_filename,
    }


@pytest.mark.asyncio
async def test_submit_valid_application():
    """A complete, valid application with an uploaded CV should succeed."""
    filename = f"{uuid.uuid4()}.pdf"
    key = f"trainers/{filename}"
    _MOCK_S3[key] = StoredObject(
        key=key,
        content=b"%PDF-1.4 fake data",
        content_type="application/pdf",
        content_length=18
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/trainers/apply", json=_valid_payload(filename))
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["full_name"] == "Grace Wanjiru"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_submit_missing_required_fields():
    """Missing required fields must return 422 validation error."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/trainers/apply", json={
            "full_name": "Only Name",
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_invalid_email():
    """Malformed email must be rejected at schema level."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = _valid_payload("fake.pdf")
        payload["email"] = "not-an-email"
        resp = await client.post("/api/v1/trainers/apply", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_nonexistent_cv():
    """Referencing a CV file that was never uploaded must return 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = _valid_payload(f"{uuid.uuid4()}.pdf")
        resp = await client.post("/api/v1/trainers/apply", json=payload)
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower() or "cv" in resp.json()["detail"].lower()


# ──────────────────────────────────────────────────────────────
# 3. Admin — List Applications (auth required)
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_applications_requires_auth():
    """Unauthenticated request must return 401 or 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/trainers/applications")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_applications_superuser():
    """Authorized superuser must be able to list applications."""
    app.dependency_overrides[get_current_active_superuser] = mock_superuser
    app.dependency_overrides[get_current_active_user] = mock_superuser
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/trainers/applications")
    assert resp.status_code == 200, resp.text


# ──────────────────────────────────────────────────────────────
# 4. Admin — Status Update (auth + validation)
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_status_requires_auth():
    """Status update without auth must be rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/trainers/applications/{uuid.uuid4()}/status",
            json={"status": "approved"},
        )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_update_status_invalid_status_value_rejected():
    """Even with a valid token, passing an invalid status value must return 422."""
    app.dependency_overrides[get_current_active_superuser] = mock_superuser
    app.dependency_overrides[get_current_active_user] = mock_superuser
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/trainers/applications/{uuid.uuid4()}/status",
            json={"status": "hacked"},
        )
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────
# 5. CV Download — auth required
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_cv_requires_auth():
    """CV download without auth must return 401 or 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/trainers/applications/{uuid.uuid4()}/cv")
    assert resp.status_code in (401, 403)
