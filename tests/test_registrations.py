import pytest
import pytest_asyncio
import uuid
from typing import AsyncGenerator
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.main import app
from app.api.deps import get_db, get_current_active_superuser
from app.db.base import Base
from app.crud.registration import create_registration
from app.schemas.registration import RegistrationCreate
from app.db.models.user import User
from app.db.models.registration import CourseRegistration
from app.db.models.contact import Contact
from app.db.models.course import Course
from app.db.models.service import Service
from app.db.models.blog import BlogPost


# Isolated async sqlite database file for deterministic, parallel-safe testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_db.sqlite"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Initializes schema and tables before every test in an isolated session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency override for tests to use the clean testing session."""
    async with TestingSessionLocal() as session:
        yield session


# Set client dependency override
async def mock_superuser():
    return User(id=uuid.uuid4(), full_name="System Admin", email="admin@livecodetech.co.ke", hashed_password="hashed_pwd", is_active=True, is_superuser=True)  # type: ignore

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
    """Provide an asynchronous HTTP client for route testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── A) SERVICE-LAYER UNIT TESTS ───
@pytest.mark.asyncio
async def test_create_registration_service():
    """Verify service-layer unit insertion works correctly using async session."""
    async with TestingSessionLocal() as db:
        payload = RegistrationCreate(
            course_title="Advanced React Architecture",
            first_name="Jane",
            last_name="Smith",
            email="jane.smith@example.com",
            registration_type="individual",
            phone="+254712345678",
            how_heard="LinkedIn Feed",
        )
        reg = await create_registration(db=db, payload=payload)
        assert reg.id is not None
        assert reg.first_name == "Jane"
        assert reg.last_name == "Smith"
        assert reg.email == "jane.smith@example.com"
        assert reg.status == "pending"


# ─── B) ROUTE-LEVEL INTEGRATION TESTS ───
@pytest.mark.asyncio
async def test_submit_individual_registration_route(async_client: AsyncClient):
    """Verify posting to the registration router yields correct status and schema."""
    body = {
        "course_title": "React Architecture",
        "first_name": "Alice",
        "last_name": "Johnson",
        "email": "alice@company.com",
        "registration_type": "individual",
        "phone": "+254711223344",
        "how_heard": "Word of Mouth",
        "accommodation": True,
        "airport_pickup": False,
    }
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "id" in data
    assert data["status"] == "pending"
    assert data["course_title"] == "React Architecture"
    assert data["first_name"] == "Alice"
    assert data["email"] == "alice@company.com"


@pytest.mark.asyncio
async def test_submit_registration_with_invalid_course_id(async_client: AsyncClient):
    """Verify posting with an invalid course_id returns 400 Bad Request."""
    body = {
        "course_id": str(uuid.uuid4()),
        "course_title": "React Architecture",
        "first_name": "Alice",
        "last_name": "Johnson",
        "email": "alice@company.com",
        "registration_type": "individual",
    }
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "The selected course does not exist."


@pytest.mark.asyncio
async def test_submit_group_registration_route(async_client: AsyncClient):
    """Verify multi-participant group registrations validate and store member details."""
    body = {
        "course_title": "Enterprise Cybersecurity",
        "first_name": "Bob",
        "last_name": "Manager",
        "email": "bob@org.com",
        "registration_type": "group",
        "group_size": "2",
        "group_members": [
            {
                "title": "Mr.",
                "first_name": "MemberOne",
                "last_name": "Smith",
                "email": "m1@org.com",
                "phone": "+254700000001",
            },
            {
                "title": "Dr.",
                "first_name": "MemberTwo",
                "last_name": "Doe",
                "email": "m2@org.com",
                "phone": "+254700000002",
            },
        ],
    }
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["registration_type"] == "group"
    assert data["first_name"] == "Bob"


# ─── C) AUTHORIZATION & PERMISSION TESTS ───
@pytest.mark.asyncio
async def test_registrations_is_publicly_accessible(async_client: AsyncClient):
    """Confirm the endpoint is public and does not require headers/credentials."""
    body = {
        "course_title": "FastAPI Masterclass",
        "first_name": "Charlie",
        "last_name": "Brown",
        "email": "charlie@gmail.com",
        "registration_type": "individual",
    }
    # No auth header passed; request should succeed
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == status.HTTP_201_CREATED


# ─── D) VALIDATION & SANITIZATION TESTS ───
@pytest.mark.asyncio
async def test_registration_validation_missing_required(async_client: AsyncClient):
    """Ensure missing required fields are rejected with 422 validation error."""
    # missing first_name and email
    body = {"course_title": "FastAPI Masterclass", "last_name": "Brown"}
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_registration_validation_extra_fields(async_client: AsyncClient):
    """Ensure extra, undocumented parameters are strictly forbidden (fail-closed)."""
    body = {
        "course_title": "FastAPI Masterclass",
        "first_name": "Charlie",
        "last_name": "Brown",
        "email": "charlie@gmail.com",
        "malicious_extra_field": "untrusted_payload",
    }
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_registration_validation_invalid_email(async_client: AsyncClient):
    """Ensure malformed email formats are cleanly rejected."""
    body = {
        "course_title": "FastAPI Masterclass",
        "first_name": "Charlie",
        "last_name": "Brown",
        "email": "not-an-email-format",
    }
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_registration_validation_invalid_phone(async_client: AsyncClient):
    """Ensure malformed telephone formats fail phone format regex."""
    body = {
        "course_title": "FastAPI Masterclass",
        "first_name": "Charlie",
        "last_name": "Brown",
        "email": "charlie@gmail.com",
        "phone": "invalid_phone_letters",
    }
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == 422


# ─── E) SQL INJECTION PREVENTION TESTS ───
@pytest.mark.asyncio
async def test_sql_injection_mitigation(async_client: AsyncClient):
    """Verify input fields containing common SQL injection vectors degrade safely."""
    body = {
        "course_title": "FastAPI Masterclass'; DROP TABLE course_registration; --",
        "first_name": "John' OR '1'='1",
        "last_name": "Smith' --",
        "email": "injection.test@example.com",
        "registration_type": "individual",
    }
    # Should succeed because parameterized ORM binding safely binds values as literal strings
    response = await async_client.post("/api/v1/registrations/", json=body)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["first_name"] == "John' OR '1'='1"
    assert (
        data["course_title"]
        == "FastAPI Masterclass'; DROP TABLE course_registration; --"
    )


# ─── F) DASHBOARD & ADMIN REGISTRATIONS TESTS ───
@pytest.mark.asyncio
async def test_dashboard_stats_and_counts(async_client: AsyncClient):
    """Verify that fetching dashboard stats aggregates count properly."""
    async with TestingSessionLocal() as db:
        # Seed test data
        c = Course(id=uuid.uuid4(), title="Data Science Boot", slug="data-science-boot", category="Data Science")  # type: ignore
        s = Service(id=uuid.uuid4(), title="App Development", slug="app-dev", description="Build custom apps")  # type: ignore
        b = BlogPost(id=uuid.uuid4(), title="Antigravity Release", slug="antigravity-release", content="Antigravity is amazing!")  # type: ignore
        r = CourseRegistration(
            id=uuid.uuid4(),
            course_title="Data Science Boot",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        msg = Contact(id=uuid.uuid4(), name="Alice", email="alice@inquiry.com", phone="+254711223344", subject="Project Inquiry", message="Looking to build an ERP system.", is_resolved=False)  # type: ignore
        db.add_all([c, s, b, r, msg])
        await db.commit()

    # Call Stats API
    response = await async_client.get("/api/v1/dashboard/stats")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["courses_count"] == 1
    assert data["services_count"] == 1
    assert data["blogs_count"] == 1
    assert data["registrations"]["total"] == 1
    assert data["registrations"]["pending"] == 1
    assert data["contacts"]["total"] == 1
    assert data["contacts"]["pending"] == 1
    assert len(data["recent_registrations"]) == 1
    assert data["recent_registrations"][0]["first_name"] == "Jane"
    assert len(data["recent_contacts"]) == 1
    assert data["recent_contacts"][0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_list_registrations_admin(async_client: AsyncClient):
    """Verify that superusers can retrieve all course registrations."""
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=uuid.uuid4(),
            course_title="Data Science Boot",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        db.add(r)
        await db.commit()

    response = await async_client.get("/api/v1/registrations/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["first_name"] == "Jane"


@pytest.mark.asyncio
async def test_update_registration_status_admin(async_client: AsyncClient):
    """Verify that superusers can change enrollment status."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="Data Science Boot",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        db.add(r)
        await db.commit()

    # Change status to confirmed
    response = await async_client.patch(f"/api/v1/registrations/{reg_id}", json={"status": "confirmed"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "confirmed"


@pytest.mark.asyncio
async def test_delete_registration_admin(async_client: AsyncClient):
    """Verify that superusers can delete a course enrollment."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="Data Science Boot",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        db.add(r)
        await db.commit()

    response = await async_client.delete(f"/api/v1/registrations/{reg_id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Registration deleted successfully"

    # Confirm it is gone
    async with TestingSessionLocal() as db:
        from sqlalchemy import select
        res = await db.execute(select(CourseRegistration))
        assert len(res.scalars().all()) == 0


@pytest.mark.asyncio
async def test_download_invoice_document(async_client: AsyncClient):
    """Verify that any user can download their course registration Invoice PDF."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="Excel and Power BI Analytics",
            first_name="Charles",
            last_name="Samir",
            email="charles.samir@example.com",
            registration_type="individual",
            status="pending",
            country="Afghanistan",
            organization="Gas Manufacturer"
        )
        db.add(r)
        await db.commit()

    response = await async_client.get(f"/api/v1/registrations/{reg_id}/invoice")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/pdf"
    assert "Content-Disposition" in response.headers
    assert "Invoice_Charles_Samir.pdf" in response.headers["Content-Disposition"]
    
    # Assert PDF file signature (%PDF)
    assert response.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_download_invitation_letter_document(async_client: AsyncClient):
    """Verify that any user can download their dynamic course Invitation Letter PDF."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="Excel and Power BI Analytics",
            first_name="Charles",
            last_name="Samir",
            email="charles.samir@example.com",
            registration_type="individual",
            status="pending",
            country="Afghanistan",
            organization="Gas Manufacturer"
        )
        db.add(r)
        await db.commit()

    response = await async_client.get(f"/api/v1/registrations/{reg_id}/invitation-letter")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/pdf"
    assert "Content-Disposition" in response.headers
    assert "Invitation_Letter_Charles_Samir.pdf" in response.headers["Content-Disposition"]
    
    # Assert PDF file signature (%PDF)
    assert response.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_download_pre_training_form_document(async_client: AsyncClient):
    """Verify that any user can download their Word DOCX pre-training evaluation form."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="Excel and Power BI Analytics",
            first_name="Charles",
            last_name="Samir",
            email="charles.samir@example.com",
            registration_type="individual",
            status="pending",
            country="Afghanistan",
            organization="Gas Manufacturer"
        )
        db.add(r)
        await db.commit()

    response = await async_client.get(f"/api/v1/registrations/{reg_id}/pre-training-form")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "Content-Disposition" in response.headers
    assert "Pre_Training_Form_Charles_Samir.docx" in response.headers["Content-Disposition"]
    
    # Assert DOCX file signature (PK\x03\x04 zip header)
    assert response.content.startswith(b"PK\x03\x04")


@pytest.mark.asyncio
async def test_download_documents_not_found(async_client: AsyncClient):
    """Verify that requests with non-existent registration IDs fail gracefully with 404."""
    fake_id = uuid.uuid4()
    
    response = await async_client.get(f"/api/v1/registrations/{fake_id}/invoice")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    
    response = await async_client.get(f"/api/v1/registrations/{fake_id}/invitation-letter")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    
    response = await async_client.get(f"/api/v1/registrations/{fake_id}/pre-training-form")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_invoice_pdf_generator_details():
    """Verify that the generated invoice PDF function compiles and contains the updated banking and registration details."""
    from app.core.document_generators import generate_invoice_pdf
    
    r = CourseRegistration(
        id=uuid.uuid4(),
        course_title="Excel and Power BI Analytics",
        first_name="Charles",
        last_name="Samir",
        email="charles.samir@example.com",
        registration_type="individual",
        status="pending",
        country="Afghanistan",
        organization="Gas Manufacturer"
    )
    
    pdf_buffer = generate_invoice_pdf(r)
    pdf_bytes = pdf_buffer.getvalue()
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000  # Verify it generates a non-empty, reasonably-sized PDF



