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
from app.db.models.course import Course


TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_courses_db.sqlite"

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


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_active_superuser] = mock_superuser


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ────────────────────────────────────────────────────────────────────────────
# A) SERVICE-LAYER UNIT TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_course_service_layer():
    """Verify the CRUD layer inserts a course correctly including sub_category."""
    from app import crud, schemas

    async with TestingSessionLocal() as db:
        payload = schemas.CourseCreate(
            title="ODK Fundamentals",
            slug="odk-fundamentals",
            category="Mobile Data Collection",
            sub_category="ODK Training Courses",
        )
        course = await crud.course.create(db, obj_in=payload)
        assert course.id is not None
        assert course.title == "ODK Fundamentals"
        assert course.slug == "odk-fundamentals"
        assert course.category == "Mobile Data Collection"
        assert course.sub_category == "ODK Training Courses"


@pytest.mark.asyncio
async def test_update_course_service_layer():
    """Verify that only supplied fields are updated via exclude_unset."""
    from app import crud, schemas

    async with TestingSessionLocal() as db:
        original = schemas.CourseCreate(
            title="Original Title",
            slug="original-title",
            category="Technical Courses",
            sub_category="GIS Training Courses",
        )
        course = await crud.course.create(db, obj_in=original)
        assert course.sub_category == "GIS Training Courses"

        update = schemas.CourseUpdate(sub_category="Digital Marketing Training Courses")
        updated = await crud.course.update(db, db_obj=course, obj_in=update)
        assert updated.sub_category == "Digital Marketing Training Courses"
        # Original fields must be untouched
        assert updated.title == "Original Title"
        assert updated.category == "Technical Courses"


# ────────────────────────────────────────────────────────────────────────────
# B) ROUTE-LEVEL INTEGRATION TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_course_route(async_client: AsyncClient):
    """POST /courses/ creates a course and returns sub_category in the response."""
    payload = {
        "title": "KoBoToolbox Advanced",
        "slug": "kobotoolbox-advanced",
        "category": "Mobile Data Collection",
        "sub_category": "KoBoToolbox Training Courses",
    }
    response = await async_client.post("/api/v1/courses/", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["title"] == "KoBoToolbox Advanced"
    assert data["slug"] == "kobotoolbox-advanced"
    assert data["sub_category"] == "KoBoToolbox Training Courses"


@pytest.mark.asyncio
async def test_create_course_without_sub_category(async_client: AsyncClient):
    """POST /courses/ succeeds when sub_category is omitted (it is optional)."""
    payload = {
        "title": "Networking Basics",
        "slug": "networking-basics",
        "category": "Computer Science and IT",
    }
    response = await async_client.post("/api/v1/courses/", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["slug"] == "networking-basics"
    # sub_category should be null/None when not supplied
    assert data.get("sub_category") in (None, "")


@pytest.mark.asyncio
async def test_read_course_by_slug(async_client: AsyncClient):
    """GET /courses/{slug} returns the correct course with sub_category."""
    payload = {
        "title": "GIS Fundamentals",
        "slug": "gis-fundamentals",
        "category": "Technical Courses",
        "sub_category": "GIS Training Courses",
    }
    await async_client.post("/api/v1/courses/", json=payload)

    response = await async_client.get("/api/v1/courses/gis-fundamentals")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["sub_category"] == "GIS Training Courses"


@pytest.mark.asyncio
async def test_read_course_by_slug_is_case_insensitive(async_client: AsyncClient):
    """GET /courses/{slug} resolves migrated slugs even when URL casing differs."""
    payload = {
        "title": "Climate Finance",
        "slug": "Climate-Finance-Course",
        "category": "Technical Courses",
        "sub_category": "Finance Training Courses",
    }
    await async_client.post("/api/v1/courses/", json=payload)

    response = await async_client.get("/api/v1/courses/climate-finance-course")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["slug"] == "Climate-Finance-Course"


@pytest.mark.asyncio
async def test_update_course_sub_category_only(async_client: AsyncClient):
    """PUT /courses/{id} with only sub_category leaves other fields intact (partial update)."""
    create_payload = {
        "title": "WordPress Basics",
        "slug": "wordpress-basics",
        "category": "Web Design & Development",
        "sub_category": "Joomla! 3.x Training Courses",
    }
    create_response = await async_client.post("/api/v1/courses/", json=create_payload)
    assert create_response.status_code == status.HTTP_200_OK
    course_id = create_response.json()["id"]

    update_payload = {"sub_category": "WordPress Training Courses"}
    update_response = await async_client.put(f"/api/v1/courses/{course_id}", json=update_payload)
    assert update_response.status_code == status.HTTP_200_OK
    updated = update_response.json()
    assert updated["sub_category"] == "WordPress Training Courses"
    # Title and category must remain unchanged
    assert updated["title"] == "WordPress Basics"
    assert updated["category"] == "Web Design & Development"


@pytest.mark.asyncio
async def test_list_courses_returns_sub_category(async_client: AsyncClient):
    """GET /courses/ returns a list where each item includes sub_category."""
    await async_client.post("/api/v1/courses/", json={
        "title": "Project Management Pro",
        "slug": "pm-pro",
        "category": "Management and Leadership",
        "sub_category": "Project Management Training Courses",
    })
    response = await async_client.get("/api/v1/courses/")
    assert response.status_code == status.HTTP_200_OK
    courses = response.json()
    assert len(courses) >= 1
    match = next((c for c in courses if c["slug"] == "pm-pro"), None)
    assert match is not None
    assert match["sub_category"] == "Project Management Training Courses"


@pytest.mark.asyncio
async def test_delete_course_route(async_client: AsyncClient):
    """DELETE /courses/{id} removes the course cleanly."""
    create_response = await async_client.post("/api/v1/courses/", json={
        "title": "Delete Me",
        "slug": "delete-me-course",
        "category": "Technical Courses",
    })
    assert create_response.status_code == status.HTTP_200_OK
    course_id = create_response.json()["id"]

    del_response = await async_client.delete(f"/api/v1/courses/{course_id}")
    assert del_response.status_code == status.HTTP_200_OK

    get_response = await async_client.get("/api/v1/courses/delete-me-course")
    assert get_response.status_code == status.HTTP_404_NOT_FOUND


# ────────────────────────────────────────────────────────────────────────────
# C) AUTHORIZATION & PERMISSION TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_course_list_is_public(async_client: AsyncClient):
    """GET /courses/ must be publicly accessible without credentials."""
    # No auth header - should succeed
    response = await async_client.get("/api/v1/courses/")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_create_requires_superuser(async_client: AsyncClient):
    """POST /courses/ must be blocked for unauthenticated callers."""
    # Remove override temporarily to simulate unauthenticated caller
    original = app.dependency_overrides.pop(get_current_active_superuser, None)
    try:
        response = await async_client.post("/api/v1/courses/", json={
            "title": "Should Not Create",
            "slug": "should-not-create",
            "category": "Technical Courses",
        })
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
    finally:
        if original is not None:
            app.dependency_overrides[get_current_active_superuser] = original


@pytest.mark.asyncio
async def test_update_requires_superuser(async_client: AsyncClient):
    """PUT /courses/{id} must be blocked for unauthenticated callers."""
    create_response = await async_client.post("/api/v1/courses/", json={
        "title": "Auth Test Course",
        "slug": "auth-test-course",
        "category": "Technical Courses",
    })
    course_id = create_response.json()["id"]

    original = app.dependency_overrides.pop(get_current_active_superuser, None)
    try:
        response = await async_client.put(f"/api/v1/courses/{course_id}", json={"sub_category": "GIS Training Courses"})
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
    finally:
        if original is not None:
            app.dependency_overrides[get_current_active_superuser] = original


# ────────────────────────────────────────────────────────────────────────────
# D) VALIDATION & SANITIZATION TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_course_missing_required_fields(async_client: AsyncClient):
    """POST /courses/ is rejected when required fields (title, slug, category) are missing."""
    response = await async_client.post("/api/v1/courses/", json={
        "sub_category": "GIS Training Courses",
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_create_course_duplicate_slug(async_client: AsyncClient):
    """POST /courses/ is rejected with 400 when slug already exists."""
    payload = {
        "title": "ODK Course",
        "slug": "odk-duplicate-slug",
        "category": "Mobile Data Collection",
    }
    first = await async_client.post("/api/v1/courses/", json=payload)
    assert first.status_code == status.HTTP_200_OK

    second = await async_client.post("/api/v1/courses/", json=payload)
    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert "slug" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_nonexistent_course(async_client: AsyncClient):
    """PUT /courses/{id} with a non-existent ID returns 404."""
    fake_id = uuid.uuid4()
    response = await async_client.put(f"/api/v1/courses/{fake_id}", json={"sub_category": "GIS Training Courses"})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_nonexistent_course_slug(async_client: AsyncClient):
    """GET /courses/{slug} for a non-existent slug returns 404."""
    response = await async_client.get("/api/v1/courses/this-does-not-exist")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_sub_category_is_optional_string(async_client: AsyncClient):
    """sub_category must be a string; integers are coerced or rejected gracefully."""
    payload = {
        "title": "Type Test Course",
        "slug": "type-test-course",
        "category": "Technical Courses",
        "sub_category": 12345,  # wrong type
    }
    # Pydantic coerces int to str; the request should still succeed
    response = await async_client.post("/api/v1/courses/", json=payload)
    # Either succeeds with coercion or fails with 422 — both are acceptable safe behaviors
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_422_UNPROCESSABLE_ENTITY)


# ────────────────────────────────────────────────────────────────────────────
# E) SQL INJECTION PREVENTION TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sql_injection_in_sub_category(async_client: AsyncClient):
    """Verify SQL injection vectors in sub_category are stored as literal strings."""
    injection = "ODK'; DROP TABLE course; --"
    payload = {
        "title": "Injection Test",
        "slug": "injection-test-sub",
        "category": "Mobile Data Collection",
        "sub_category": injection,
    }
    response = await async_client.post("/api/v1/courses/", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # The string is stored verbatim — the table must still exist for this to succeed
    assert data["sub_category"] == injection

    # Confirm the course table still exists and is queryable
    list_response = await async_client.get("/api/v1/courses/")
    assert list_response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_sql_injection_in_title_and_slug(async_client: AsyncClient):
    """Verify SQL injection in title/slug fields is safely handled by the ORM."""
    payload = {
        "title": "Title'; DROP TABLE course; --",
        "slug": "safe-slug-inject",
        "category": "Technical Courses",
    }
    response = await async_client.post("/api/v1/courses/", json=payload)
    assert response.status_code == status.HTTP_200_OK
    # The table must still function — parameterized bindings prevented damage
    list_response = await async_client.get("/api/v1/courses/")
    assert list_response.status_code == status.HTTP_200_OK
    courses = list_response.json()
    match = next((c for c in courses if c["slug"] == "safe-slug-inject"), None)
    assert match is not None
    assert match["title"] == "Title'; DROP TABLE course; --"


@pytest.mark.asyncio
async def test_sql_injection_in_slug_path_param(async_client: AsyncClient):
    """Verify path-parameter slug injection degrades safely (404, not 500)."""
    malicious_slug = "'; DROP TABLE course; --"
    response = await async_client.get(f"/api/v1/courses/{malicious_slug}")
    # Must return 404 (not found) or 422, never 500
    assert response.status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
