import pytest
import pytest_asyncio
import uuid
from unittest.mock import patch
from typing import AsyncGenerator
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.main import app
from app.api.deps import get_db, get_current_active_superuser, get_current_active_admin
from app.db.base import Base
from app.db.models.user import User
from app.db.models.course import Course


TEST_DATABASE_URL = "sqlite+aiosqlite:///./tests/test_courses_db.sqlite"

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


STATIC_USER_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")

async def mock_superuser():
    return User(
        id=STATIC_USER_ID,
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
    app.dependency_overrides[get_current_active_admin] = mock_superuser
    yield
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]
    if get_current_active_superuser in app.dependency_overrides:
        del app.dependency_overrides[get_current_active_superuser]
    if get_current_active_admin in app.dependency_overrides:
        del app.dependency_overrides[get_current_active_admin]


@pytest_asyncio.fixture(autouse=True)
async def mock_redis_for_drafts():
    fake_redis = {}

    async def fake_get(key: str):
        return fake_redis.get(key)

    async def fake_set(key: str, value: str, expire: int = 3600):
        fake_redis[key] = value
        return True

    async def fake_delete(key: str):
        fake_redis.pop(key, None)
        return True

    with patch("app.core.redis.redis_manager.get", side_effect=fake_get), \
         patch("app.core.redis.redis_manager.set", side_effect=fake_set), \
         patch("app.core.redis.redis_manager.delete", side_effect=fake_delete):
        yield


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
async def test_list_courses_can_filter_by_category_and_sub_category(async_client: AsyncClient):
    """GET /courses/ supports navbar category/subcategory filters."""
    await async_client.post("/api/v1/courses/", json={
        "title": "ODK Basics",
        "slug": "odk-basics",
        "category": "Mobile Data Collection",
        "sub_category": "ODK Training Courses",
    })
    await async_client.post("/api/v1/courses/", json={
        "title": "KoBo Basics",
        "slug": "kobo-basics",
        "category": "Mobile Data Collection",
        "sub_category": "KoBoToolbox Training Courses",
    })

    response = await async_client.get(
        "/api/v1/courses/",
        params={
            "category": "Mobile Data Collection",
            "sub_category": "ODK Training Courses",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    courses = response.json()
    assert [course["slug"] for course in courses] == ["odk-basics"]


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


@pytest.mark.asyncio
async def test_list_courses_summary(async_client: AsyncClient):
    """Verify GET /courses/ with summary=true excludes curriculum_blocks."""
    payload = {
        "title": "Summary Test Course",
        "slug": "summary-test-course",
        "category": "Technical Courses",
        "curriculum_blocks": [
            {
                "type": "paragraph",
                "content": {"text": "This is heavy curriculum content"},
                "order_index": 0
            }
        ]
    }
    create_response = await async_client.post("/api/v1/courses/", json=payload)
    assert create_response.status_code == status.HTTP_200_OK

    # 1. Fetch with summary=true
    response_summary = await async_client.get("/api/v1/courses/", params={"summary": "true"})
    assert response_summary.status_code == status.HTTP_200_OK
    courses_summary = response_summary.json()
    match_summary = next((c for c in courses_summary if c["slug"] == "summary-test-course"), None)
    assert match_summary is not None
    assert "curriculum_blocks" not in match_summary

    # 2. Fetch with summary=false (default)
    response_full = await async_client.get("/api/v1/courses/")
    assert response_full.status_code == status.HTTP_200_OK
    courses_full = response_full.json()
    match_full = next((c for c in courses_full if c["slug"] == "summary-test-course"), None)
    assert match_full is not None
    assert len(match_full.get("curriculum_blocks", [])) == 1
    assert match_full["curriculum_blocks"][0]["content"]["text"] == "This is heavy curriculum content"


@pytest.mark.asyncio
async def test_list_courses_active_only(async_client: AsyncClient):
    """Verify that GET /courses/ with active_only=true filters out expired/no-schedule courses."""
    from datetime import datetime
    current_year = datetime.now().year
    future_year = current_year + 1
    past_year = current_year - 5

    # 1. Course with future schedule
    active_payload = {
        "title": "Active Course",
        "slug": "active-course",
        "category": "Technical Courses",
        "schedules": [
            {
                "date_range": f"18 May - 29 May {future_year}",
                "location": "Nairobi",
                "mode": "physical",
                "year": future_year
            }
        ]
    }
    # 2. Course with expired schedule
    expired_payload = {
        "title": "Expired Course",
        "slug": "expired-course",
        "category": "Technical Courses",
        "schedules": [
            {
                "date_range": f"01 Jan - 10 Jan {past_year}",
                "location": "Mombasa",
                "mode": "physical",
                "year": past_year
            }
        ]
    }
    # 3. Course with no schedules
    no_sched_payload = {
        "title": "No Sched Course",
        "slug": "no-sched-course",
        "category": "Technical Courses",
        "schedules": []
    }

    res_active = await async_client.post("/api/v1/courses/", json=active_payload)
    assert res_active.status_code == status.HTTP_200_OK
    res_expired = await async_client.post("/api/v1/courses/", json=expired_payload)
    assert res_expired.status_code == status.HTTP_200_OK
    res_no_sched = await async_client.post("/api/v1/courses/", json=no_sched_payload)
    assert res_no_sched.status_code == status.HTTP_200_OK

    # Fetch with active_only=true
    resp_active_only = await async_client.get("/api/v1/courses/", params={"active_only": "true"})
    assert resp_active_only.status_code == status.HTTP_200_OK
    courses_active = resp_active_only.json()
    slugs_active = [c["slug"] for c in courses_active]

    assert "active-course" in slugs_active
    assert "expired-course" not in slugs_active
    assert "no-sched-course" not in slugs_active

    # Fetch with active_only=false (should return all courses)
    resp_all = await async_client.get("/api/v1/courses/", params={"active_only": "false"})
    assert resp_all.status_code == status.HTTP_200_OK
    courses_all = resp_all.json()
    slugs_all = [c["slug"] for c in courses_all]

    assert "active-course" in slugs_all
    assert "expired-course" in slugs_all
    assert "no-sched-course" in slugs_all


@pytest.mark.asyncio
async def test_list_courses_active_only_respects_enabled(async_client: AsyncClient):
    """Verify active_only=true excludes courses whose only future schedule is disabled."""
    from datetime import datetime
    future_year = datetime.now().year + 1

    # Course whose sole schedule is future but explicitly disabled
    disabled_payload = {
        "title": "Disabled Future Course",
        "slug": "disabled-future-course",
        "category": "Technical Courses",
        "schedules": [
            {
                "date_range": f"01 Jun - 10 Jun {future_year}",
                "location": "Nairobi",
                "mode": "physical",
                "year": future_year,
                "enabled": False,
            }
        ],
    }
    # Course with one disabled future + one enabled future schedule (should still appear)
    mixed_payload = {
        "title": "Mixed Schedule Course",
        "slug": "mixed-schedule-course",
        "category": "Technical Courses",
        "schedules": [
            {
                "date_range": f"01 Jul - 05 Jul {future_year}",
                "location": "Mombasa",
                "mode": "physical",
                "year": future_year,
                "enabled": False,
            },
            {
                "date_range": f"15 Aug - 20 Aug {future_year}",
                "location": "Kisumu",
                "mode": "virtual",
                "year": future_year,
                "enabled": True,
            },
        ],
    }

    res_disabled = await async_client.post("/api/v1/courses/", json=disabled_payload)
    assert res_disabled.status_code == status.HTTP_200_OK
    res_mixed = await async_client.post("/api/v1/courses/", json=mixed_payload)
    assert res_mixed.status_code == status.HTTP_200_OK

    resp = await async_client.get("/api/v1/courses/", params={"active_only": "true"})
    assert resp.status_code == status.HTTP_200_OK
    slugs = [c["slug"] for c in resp.json()]

    # Disabled-only course must be filtered out
    assert "disabled-future-course" not in slugs
    # Mixed course still has an enabled future schedule — must appear
    assert "mixed-schedule-course" in slugs


@pytest.mark.asyncio
async def test_enabled_field_persisted_on_create(async_client: AsyncClient):
    """Verify enabled=False is stored and returned correctly on course creation."""
    from datetime import datetime
    future_year = datetime.now().year + 1

    payload = {
        "title": "Persist Enabled Test",
        "slug": "persist-enabled-test",
        "category": "Technical Courses",
        "schedules": [
            {
                "date_range": f"01 Sep - 10 Sep {future_year}",
                "location": "Nairobi",
                "mode": "physical",
                "year": future_year,
                "enabled": False,
            }
        ],
    }
    create_resp = await async_client.post("/api/v1/courses/", json=payload)
    assert create_resp.status_code == status.HTTP_200_OK

    get_resp = await async_client.get("/api/v1/courses/persist-enabled-test")
    assert get_resp.status_code == status.HTTP_200_OK
    data = get_resp.json()
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["enabled"] is False


# ────────────────────────────────────────────────────────────────────────────
# F) DRAFT PERSISTENCE TESTS
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_put_delete_course_draft(async_client: AsyncClient):
    """Verify that we can save, retrieve, and delete course drafts in Redis."""
    # 1. Get draft (should return None/null initially)
    get_resp = await async_client.get("/api/v1/courses/draft")
    assert get_resp.status_code == status.HTTP_200_OK
    assert get_resp.json() is None

    # 2. Put draft
    draft_payload = {"title": "Draft Course", "blocks": [{"type": "metadata", "title": "Draft Course"}]}
    put_resp = await async_client.put("/api/v1/courses/draft", json=draft_payload)
    assert put_resp.status_code == status.HTTP_200_OK
    assert put_resp.json() == {"status": "success"}

    # 3. Get draft (should return the saved payload)
    get_resp2 = await async_client.get("/api/v1/courses/draft")
    assert get_resp2.status_code == status.HTTP_200_OK
    assert get_resp2.json() == draft_payload

    # 4. Delete draft
    del_resp = await async_client.delete("/api/v1/courses/draft")
    assert del_resp.status_code == status.HTTP_200_OK
    assert del_resp.json() == {"status": "success"}

    # 5. Get draft (should be None/null again)
    get_resp3 = await async_client.get("/api/v1/courses/draft")
    assert get_resp3.status_code == status.HTTP_200_OK
    assert get_resp3.json() is None


@pytest.mark.asyncio
async def test_course_draft_requires_authentication(async_client: AsyncClient):
    """Verify that unauthenticated or non-admin users cannot access course draft endpoints."""
    # Remove mock admin override temporarily
    original = app.dependency_overrides.pop(get_current_active_admin, None)
    try:
        # GET draft without auth should fail
        get_resp = await async_client.get("/api/v1/courses/draft")
        assert get_resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        # PUT draft without auth should fail
        put_resp = await async_client.put("/api/v1/courses/draft", json={"title": "Draft"})
        assert put_resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        # DELETE draft without auth should fail
        del_resp = await async_client.delete("/api/v1/courses/draft")
        assert del_resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
    finally:
        if original is not None:
            app.dependency_overrides[get_current_active_admin] = original


@pytest.mark.asyncio
async def test_course_draft_sql_injection_resilience(async_client: AsyncClient):
    """Verify that draft payload is resilient to SQL injection attempts."""
    injection_data = {"sql": "'; DROP TABLE course; --", "data": "dummy"}
    put_resp = await async_client.put("/api/v1/courses/draft", json=injection_data)
    assert put_resp.status_code == status.HTTP_200_OK

    get_resp = await async_client.get("/api/v1/courses/draft")
    assert get_resp.status_code == status.HTTP_200_OK
    assert get_resp.json() == injection_data

    # Verify database table is still queryable and unaffected
    list_response = await async_client.get("/api/v1/courses/")
    assert list_response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_course_search_and_pagination_headers(async_client: AsyncClient):
    """Verify that courses search query returns correct matches and sets X-Total-Count headers."""
    # 1. Verify default courses list returns X-Total-Count header
    list_response = await async_client.get("/api/v1/courses/")
    assert list_response.status_code == status.HTTP_200_OK
    assert "X-Total-Count" in list_response.headers
    
    # 2. Search for a specific query that matches nothing
    search_response = await async_client.get("/api/v1/courses/", params={"search": "completely_nonexistent_search_query"})
    assert search_response.status_code == status.HTTP_200_OK
    assert search_response.headers["X-Total-Count"] == "0"
    assert len(search_response.json()) == 0

    # 3. Test caching behavior with search params
    # Initial request sets the cache
    first_resp = await async_client.get("/api/v1/courses/", params={"search": "fundamentals"})
    assert first_resp.status_code == status.HTTP_200_OK
    count_matches = first_resp.headers["X-Total-Count"]
    
    # Second request retrieves from cache, checking if header is successfully mapped
    second_resp = await async_client.get("/api/v1/courses/", params={"search": "fundamentals"})
    assert second_resp.status_code == status.HTTP_200_OK
    assert second_resp.headers["X-Total-Count"] == count_matches


@pytest.mark.asyncio
async def test_course_categories_endpoint(async_client: AsyncClient):
    """Verify that courses categories endpoint returns structured categories and subcategories."""
    response = await async_client.get("/api/v1/courses/categories")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "category" in data[0]
        assert "sub_categories" in data[0]
        assert isinstance(data[0]["sub_categories"], list)

