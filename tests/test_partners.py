import pytest
import pytest_asyncio
import uuid
from typing import AsyncGenerator
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.main import app
from app.api.deps import get_db, get_current_active_superuser
from app.db.base import Base
from app.db.models.user import User
from app.db.models.partner import TrustedPartner


TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_partners_db.sqlite"

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


@pytest_asyncio.fixture(autouse=True)
async def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_superuser] = mock_superuser
    yield
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]
    if get_current_active_superuser in app.dependency_overrides:
        del app.dependency_overrides[get_current_active_superuser]


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ────────────────────────────────────────────────────────────────────────────
# A) SERVICE-LAYER UNIT TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_partner_service_layer():
    """Verify the CRUD layer inserts a partner correctly."""
    from app import crud, schemas

    async with TestingSessionLocal() as db:
        payload = schemas.TrustedPartnerCreate(
            name="Test Partner",
            logo_url="/static/test.png",
            website_url="https://test.partner.org",
            display_order=5,
            is_active=True,
        )
        partner = await crud.trusted_partner.create(db, obj_in=payload)
        assert partner.id is not None
        assert partner.name == "Test Partner"
        assert partner.logo_url == "/static/test.png"
        assert partner.website_url == "https://test.partner.org"
        assert partner.display_order == 5
        assert partner.is_active is True


@pytest.mark.asyncio
async def test_update_partner_service_layer():
    """Verify updating fields via the CRUD layer."""
    from app import crud, schemas

    async with TestingSessionLocal() as db:
        original = schemas.TrustedPartnerCreate(
            name="Original Name",
            logo_url="/static/original.png",
            display_order=0,
        )
        partner = await crud.trusted_partner.create(db, obj_in=original)
        assert partner.is_active is True

        update = schemas.TrustedPartnerUpdate(
            name="Updated Name",
            is_active=False,
        )
        updated = await crud.trusted_partner.update(db, db_obj=partner, obj_in=update)
        assert updated.name == "Updated Name"
        assert updated.is_active is False
        assert updated.logo_url == "/static/original.png"


# ────────────────────────────────────────────────────────────────────────────
# B) ROUTE-LEVEL INTEGRATION TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_partner_route(async_client: AsyncClient):
    """POST /partners/ creates a partner."""
    payload = {
        "name": "Integration Partner",
        "logo_url": "/static/logo.png",
        "website_url": "https://integration.org",
        "display_order": 1,
    }
    response = await async_client.post("/api/v1/partners/", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Integration Partner"
    assert data["logo_url"] == "/static/logo.png"


@pytest.mark.asyncio
async def test_read_active_partners_public(async_client: AsyncClient):
    """GET /partners/ retrieves active partners ordered by display_order."""
    p1 = {
        "name": "Partner A",
        "logo_url": "/static/a.png",
        "display_order": 10,
        "is_active": True,
    }
    p2 = {
        "name": "Partner B",
        "logo_url": "/static/b.png",
        "display_order": 5,
        "is_active": True,
    }
    p3 = {
        "name": "Partner C",
        "logo_url": "/static/c.png",
        "display_order": 1,
        "is_active": False,
    }
    await async_client.post("/api/v1/partners/", json=p1)
    await async_client.post("/api/v1/partners/", json=p2)
    await async_client.post("/api/v1/partners/", json=p3)

    # Public endpoint should show active only, ordered by display_order
    response = await async_client.get("/api/v1/partners/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Partner B"  # display_order 5
    assert data[1]["name"] == "Partner A"  # display_order 10


# ────────────────────────────────────────────────────────────────────────────
# C) AUTHORIZATION & PERMISSION TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_partner_requires_superuser(async_client: AsyncClient):
    """POST /partners/ must block non-superusers."""
    original = app.dependency_overrides.pop(get_current_active_superuser, None)
    try:
        response = await async_client.post("/api/v1/partners/", json={
            "name": "Unauthorized",
            "logo_url": "/static/unauthorized.png",
        })
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
    finally:
        if original is not None:
            app.dependency_overrides[get_current_active_superuser] = original


# ────────────────────────────────────────────────────────────────────────────
# D) VALIDATION & SANITIZATION TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_partner_validation_errors(async_client: AsyncClient):
    """POST /partners/ fails validation when required fields are missing."""
    # name is required
    response = await async_client.post("/api/v1/partners/", json={
        "logo_url": "/static/logo.png"
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ────────────────────────────────────────────────────────────────────────────
# E) SQL INJECTION PREVENTION TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sql_injection_in_partner_fields(async_client: AsyncClient):
    """SQL injection strings in input should be parameterized safely by the ORM."""
    injection = "Partner'; DROP TABLE trustedpartner; --"
    payload = {
        "name": injection,
        "logo_url": "/static/injection.png",
    }
    response = await async_client.post("/api/v1/partners/", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == injection

    # Table must still function and remain queryable
    list_response = await async_client.get("/api/v1/partners/")
    assert list_response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_upload_partner_logo_webp_conversion(async_client: AsyncClient):
    """POST /partners/upload-logo converts a PNG image to WebP format using FFmpeg."""
    import io
    import os
    from PIL import Image

    img = Image.new("RGB", (10, 10), color="blue")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_bytes = img_byte_arr.getvalue()

    files = {"file": ("test.png", img_bytes, "image/png")}
    response = await async_client.post("/api/v1/partners/upload-logo", files=files)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "url" in data
    # Assert URL ends with .webp, proving conversion happened!
    assert data["url"].endswith(".webp")

    # Verify the physical file exists and clean it up
    relative = data["url"].split("/media/")[-1]
    file_path = os.path.join("static", relative)
    assert os.path.isfile(file_path)
    os.remove(file_path)

