import pytest
import pytest_asyncio
import uuid
from typing import AsyncGenerator
from fastapi import status
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.deps import get_db, get_current_active_superuser
from app.db.base import Base
from app.db.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

TEST_DATABASE_URL = "sqlite+aiosqlite:///./tests/test_db.sqlite"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(autouse=True)
async def setup_db_override():
    app.dependency_overrides[get_db] = override_get_db
    yield
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]

@pytest_asyncio.fixture
async def unauthenticated_client() -> AsyncGenerator[AsyncClient, None]:
    # Ensure there is no superuser override
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
async def test_read_users_unauthenticated(unauthenticated_client: AsyncClient):
    """Verify that unauthenticated access to GET /users/ is rejected with 401."""
    response = await unauthenticated_client.get("/api/v1/users/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.asyncio
async def test_create_user_unauthenticated(unauthenticated_client: AsyncClient):
    """Verify that unauthenticated access to POST /users/ is rejected with 401."""
    payload = {
        "email": "newuser@example.com",
        "password": "password123",
        "full_name": "New User"
    }
    response = await unauthenticated_client.post("/api/v1/users/", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.asyncio
async def test_read_user_by_id_unauthenticated(unauthenticated_client: AsyncClient):
    """Verify that unauthenticated access to GET /users/{id} is rejected with 401."""
    fake_id = uuid.uuid4()
    response = await unauthenticated_client.get(f"/api/v1/users/{fake_id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

# ─── B) AUTHENTICATED TESTS ───

@pytest.mark.asyncio
async def test_read_users_authenticated(authenticated_client: AsyncClient):
    """Verify that authenticated superusers can access GET /users/ with pagination format."""
    response = await authenticated_client.get("/api/v1/users/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, dict)
    assert "users" in data
    assert "total" in data
    assert isinstance(data["users"], list)

@pytest.mark.asyncio
async def test_create_user_authenticated(authenticated_client: AsyncClient):
    """Verify that authenticated superusers can create new users."""
    payload = {
        "email": "newuser@example.com",
        "password": "password123",
        "first_name": "New",
        "last_name": "User",
        "role": "instructor"
    }
    response = await authenticated_client.post("/api/v1/users/", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["first_name"] == "New"
    assert data["last_name"] == "User"
    assert data["full_name"] == "New User"
    assert data["role"] == "instructor"
    assert "id" in data

@pytest.mark.asyncio
async def test_update_user_authenticated(authenticated_client: AsyncClient):
    """Verify that authenticated superusers can update users."""
    # 1. Create a user first
    payload = {
        "email": "updateuser@example.com",
        "password": "password123",
        "first_name": "Before",
        "last_name": "Update"
    }
    create_resp = await authenticated_client.post("/api/v1/users/", json=payload)
    assert create_resp.status_code == status.HTTP_200_OK
    user_id = create_resp.json()["id"]

    # 2. Update the user
    update_payload = {
        "first_name": "After",
        "last_name": "Update",
        "phone": "+1234567890",
        "bio": "Updated bio"
    }
    update_resp = await authenticated_client.put(f"/api/v1/users/{user_id}", json=update_payload)
    assert update_resp.status_code == status.HTTP_200_OK
    data = update_resp.json()
    assert data["first_name"] == "After"
    assert data["last_name"] == "Update"
    assert data["full_name"] == "After Update"
    assert data["phone"] == "+1234567890"
    assert data["bio"] == "Updated bio"

@pytest.mark.asyncio
async def test_delete_user_authenticated(authenticated_client: AsyncClient):
    """Verify that authenticated superusers can delete users."""
    # 1. Create a user first
    payload = {
        "email": "deleteuser@example.com",
        "password": "password123",
        "full_name": "To Be Deleted"
    }
    create_resp = await authenticated_client.post("/api/v1/users/", json=payload)
    assert create_resp.status_code == status.HTTP_200_OK
    user_id = create_resp.json()["id"]

    # 2. Delete the user
    delete_resp = await authenticated_client.delete(f"/api/v1/users/{user_id}")
    assert delete_resp.status_code == status.HTTP_200_OK

    # 3. Verify user is gone
    get_resp = await authenticated_client.get(f"/api/v1/users/{user_id}")
    assert get_resp.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_change_user_status_authenticated(authenticated_client: AsyncClient):
    """Verify that authenticated superusers can patch user status."""
    # 1. Create a user first
    payload = {
        "email": "statususer@example.com",
        "password": "password123",
        "full_name": "Status User"
    }
    create_resp = await authenticated_client.post("/api/v1/users/", json=payload)
    assert create_resp.status_code == status.HTTP_200_OK
    user_id = create_resp.json()["id"]

    # 2. Patch status to suspended
    patch_resp = await authenticated_client.patch(f"/api/v1/users/{user_id}/status", json={"status": "suspended"})
    assert patch_resp.status_code == status.HTTP_200_OK
    data = patch_resp.json()
    assert data["status"] == "suspended"

@pytest.mark.asyncio
async def test_change_user_role_authenticated(authenticated_client: AsyncClient):
    """Verify that authenticated superusers can patch user role."""
    # 1. Create a user first
    payload = {
        "email": "roleuser@example.com",
        "password": "password123",
        "full_name": "Role User"
    }
    create_resp = await authenticated_client.post("/api/v1/users/", json=payload)
    assert create_resp.status_code == status.HTTP_200_OK
    user_id = create_resp.json()["id"]

    # 2. Patch role to moderator
    patch_resp = await authenticated_client.patch(f"/api/v1/users/{user_id}/role", json={"role": "moderator"})
    assert patch_resp.status_code == status.HTTP_200_OK
    data = patch_resp.json()
    assert data["role"] == "moderator"
    assert data["is_superuser"] is False



# ─── C) BROWSER VS API ERROR RESPONSE TESTS ───

@pytest.mark.asyncio
async def test_error_response_html_for_browsers(unauthenticated_client: AsyncClient):
    """Verify that unauthenticated browser requests get the custom error HTML page."""
    headers = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}
    response = await unauthenticated_client.get("/api/v1/users/", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "text/html" in response.headers["content-type"]
    html_content = response.text
    assert "401" in html_content
    assert "Not Authenticated" in html_content
    assert "You are not authenticated to view this page" in html_content

@pytest.mark.asyncio
async def test_error_response_json_for_apis(unauthenticated_client: AsyncClient):
    """Verify that unauthenticated API requests get a standard JSON error response."""
    headers = {"accept": "application/json"}
    response = await unauthenticated_client.get("/api/v1/users/", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "application/json" in response.headers["content-type"]
    assert response.json()["detail"] == "Not authenticated"

