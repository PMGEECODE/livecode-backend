import os
import shutil
import pytest
import pytest_asyncio
import uuid
import io
from typing import AsyncGenerator
from fastapi import status
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.deps import get_db, get_current_active_superuser
from app.db.base import Base
from app.db.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_db.sqlite"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    upload_dir = "static/uploads"
    # Keep track of existing directories
    existing_dirs = set(os.listdir(upload_dir)) if os.path.exists(upload_dir) else set()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        
    if os.path.exists(upload_dir):
        for dname in os.listdir(upload_dir):
            if dname not in existing_dirs:
                try:
                    path = os.path.join(upload_dir, dname)
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception:
                    pass

async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(autouse=True)
async def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    yield
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]

@pytest_asyncio.fixture
async def unauthenticated_client() -> AsyncGenerator[AsyncClient, None]:
    if get_current_active_superuser in app.dependency_overrides:
        del app.dependency_overrides[get_current_active_superuser]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def authenticated_client() -> AsyncGenerator[AsyncClient, None]:
    async def mock_superuser():
        return User(
            id=uuid.uuid4(),
            full_name="Test Superuser",
            email="admin@example.com",
            hashed_password="password",
            is_active=True,
            is_superuser=True
        )
    app.dependency_overrides[get_current_active_superuser] = mock_superuser
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    if get_current_active_superuser in app.dependency_overrides:
        del app.dependency_overrides[get_current_active_superuser]

# ─── A) UNAUTHENTICATED TESTS ───

@pytest.mark.asyncio
async def test_upload_unauthenticated(unauthenticated_client: AsyncClient):
    """Verify that unauthenticated access to POST /upload/ is rejected with 401."""
    files = {"file": ("test.png", b"fake image bytes", "image/png")}
    response = await unauthenticated_client.post("/api/v1/upload/", files=files, data={"slug": "test-course"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

# ─── B) AUTHENTICATED TESTS & VALIDATION ───

@pytest.mark.asyncio
async def test_upload_valid_image(authenticated_client: AsyncClient):
    """Verify that an authenticated superuser can successfully upload a valid image."""
    files = {"file": ("test.png", b"fake image bytes", "image/png")}
    response = await authenticated_client.post("/api/v1/upload/", files=files, data={"slug": "test-course"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "url" in data
    assert data["url"].startswith("/api/v1/media/uploads/test-course/")
    assert data["url"].endswith(".png")

@pytest.mark.asyncio
async def test_upload_invalid_mime_type(authenticated_client: AsyncClient):
    """Verify that uploading a non-image file type is rejected with 400."""
    files = {"file": ("test.txt", b"plain text", "text/plain")}
    response = await authenticated_client.post("/api/v1/upload/", files=files, data={"slug": "test-course"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Only image files are allowed" in response.json()["detail"]

@pytest.mark.asyncio
async def test_upload_invalid_extension(authenticated_client: AsyncClient):
    """Verify that uploading an image with an unsupported file extension is rejected with 400."""
    files = {"file": ("test.exe", b"fake image bytes", "image/png")}
    response = await authenticated_client.post("/api/v1/upload/", files=files, data={"slug": "test-course"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Unsupported image format" in response.json()["detail"]

@pytest.mark.asyncio
async def test_upload_sql_injection_prevention(authenticated_client: AsyncClient):
    """Verify that malicious payload filenames do not cause SQL issues and are handled safely."""
    malicious_filename = "test'; DROP TABLE users; --.png"
    files = {"file": (malicious_filename, b"fake image bytes", "image/png")}
    response = await authenticated_client.post("/api/v1/upload/", files=files, data={"slug": "test-course-sql"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "url" in data
    # The filename generated should be a random UUID, not the malicious string
    url = data["url"]
    assert "DROP TABLE" not in url

@pytest.mark.asyncio
async def test_upload_one_image_per_course(authenticated_client: AsyncClient):
    """Verify that uploading a new image for a course deletes the previous image."""
    slug = "test-course-purge"
    
    # Upload first image
    files1 = {"file": ("image1.png", b"fake image 1 bytes", "image/png")}
    resp1 = await authenticated_client.post("/api/v1/upload/", files=files1, data={"slug": slug})
    assert resp1.status_code == status.HTTP_200_OK
    url1 = resp1.json()["url"]
    
    # Upload second image
    files2 = {"file": ("image2.jpg", b"fake image 2 bytes", "image/jpeg")}
    resp2 = await authenticated_client.post("/api/v1/upload/", files=files2, data={"slug": slug})
    assert resp2.status_code == status.HTTP_200_OK
    url2 = resp2.json()["url"]
    
    assert url1 != url2
    
    def get_disk_path(url: str) -> str:
        parts = url.split("/media/uploads/")
        if len(parts) == 2:
            return os.path.join("static", "uploads", parts[1])
        return url.lstrip("/")

    filepath1 = get_disk_path(url1)
    filepath2 = get_disk_path(url2)
    
    assert not os.path.exists(filepath1)
    assert os.path.exists(filepath2)

