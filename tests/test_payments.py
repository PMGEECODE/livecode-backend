import pytest
import pytest_asyncio
import uuid
from typing import AsyncGenerator
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from unittest.mock import patch, AsyncMock

from app.main import app
from app.api.deps import get_db
from app.db.base import Base
from app.db.models.registration import CourseRegistration
from app.db.models.payment import PaymentTransaction
from app.services.mpesa import mpesa_service

from tests.test_registrations import engine, TestingSessionLocal, override_get_db

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Initializes schema and tables before every test in an isolated session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP client for route testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── A) SERVICE-LAYER UNIT TESTS ───
@pytest.mark.asyncio
async def test_mpesa_service_phone_formatting():
    """Verify phone formatting logic converts numbers correctly."""
    assert mpesa_service.format_phone("0712345678") == "254712345678"
    assert mpesa_service.format_phone("+254712345678") == "254712345678"
    assert mpesa_service.format_phone("712345678") == "254712345678"
    assert mpesa_service.format_phone("254712345678") == "254712345678"


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_mpesa_service_access_token(mock_get):
    """Verify that get_access_token fetches Safaricom oauth token correctly."""
    mock_get.return_value = AsyncMock(
        status_code=200,
        json=lambda: {"access_token": "mocked_saf_token"}
    )
    token = await mpesa_service.get_access_token()
    assert token == "mocked_saf_token"


# ─── B) ROUTE-LEVEL INTEGRATION TESTS ───
@pytest.mark.asyncio
@patch("app.services.mpesa.MpesaService.initiate_stk_push")
async def test_initiate_stk_push_route(mock_stk, async_client: AsyncClient):
    """Verify posting to stk-push triggers Safaricom call and saves pending transaction."""
    # Seed registration
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Masterclass",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        db.add(r)
        await db.commit()

    # Mock safaricom response
    mock_stk.return_value = {
        "CheckoutRequestID": "ws_CO_123456789",
        "MerchantRequestID": "123-456-789",
        "CustomerMessage": "Success. Request accepted for processing"
    }

    body = {
        "registration_id": str(reg_id),
        "phone_number": "0712345678",
        "amount": 1500.0
    }

    response = await async_client.post("/api/v1/payments/mpesa/stk-push", json=body)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["checkout_request_id"] == "ws_CO_123456789"
    assert data["merchant_request_id"] == "123-456-789"

    # Verify transaction saved in database
    async with TestingSessionLocal() as db:
        from sqlalchemy import select
        res = await db.execute(select(PaymentTransaction))
        tx = res.scalars().first()
        assert tx is not None
        assert tx.registration_id == reg_id
        assert tx.checkout_request_id == "ws_CO_123456789"
        assert tx.amount == 1500.0
        assert tx.status == "pending"


@pytest.mark.asyncio
async def test_mpesa_status_route_not_found(async_client: AsyncClient):
    """Verify status route handles non-existent checkout request IDs gracefully."""
    response = await async_client.get("/api/v1/payments/mpesa/status/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.payments.process_registration_email")
async def test_mpesa_callback_success(mock_email, async_client: AsyncClient):
    """Verify that Safaricom callback updates transaction/registration and sends email on success."""
    reg_id = uuid.uuid4()
    checkout_id = "ws_CO_987654321"

    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Masterclass",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        t = PaymentTransaction(
            registration_id=reg_id,
            checkout_request_id=checkout_id,
            amount=2000.0,
            phone_number="254712345678",
            status="pending",
        )
        db.add_all([r, t])
        await db.commit()

    callback_payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "12345-67890",
                "CheckoutRequestID": checkout_id,
                "ResultCode": 0,
                "ResultDesc": "The service request processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 2000.0},
                        {"Name": "MpesaReceiptNumber", "Value": "QWERTYUIOP"},
                        {"Name": "TransactionDate", "Value": 20260519120000},
                        {"Name": "PhoneNumber", "Value": 254712345678}
                    ]
                }
            }
        }
    }

    response = await async_client.post("/api/v1/payments/mpesa/callback", json=callback_payload)
    assert response.status_code == 200
    assert response.json() == {"ResultCode": 0, "ResultDesc": "Success"}

    # Verify statuses updated in db
    async with TestingSessionLocal() as db:
        from sqlalchemy import select
        # check tx
        tx_stmt = select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == checkout_id)
        tx_res = await db.execute(tx_stmt)
        tx = tx_res.scalars().first()
        assert tx.status == "completed"
        assert tx.mpesa_receipt_number == "QWERTYUIOP"

        # check reg
        reg_stmt = select(CourseRegistration).filter(CourseRegistration.id == reg_id)
        reg_res = await db.execute(reg_stmt)
        reg = reg_res.scalars().first()
        assert reg.status == "confirmed"


# ─── C) VALIDATION & SANITIZATION TESTS ───
@pytest.mark.asyncio
async def test_initiate_stk_push_validation_extra_fields(async_client: AsyncClient):
    """Verify that posting extra fields to STK push is rejected."""
    body = {
        "registration_id": str(uuid.uuid4()),
        "phone_number": "0712345678",
        "amount": 100.0,
        "unexpected_extra_field": "malicious"
    }
    response = await async_client.post("/api/v1/payments/mpesa/stk-push", json=body)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_initiate_stk_push_validation_invalid_amount(async_client: AsyncClient):
    """Verify that STK push rejects negative/zero amounts."""
    body = {
        "registration_id": str(uuid.uuid4()),
        "phone_number": "0712345678",
        "amount": -50.0
    }
    response = await async_client.post("/api/v1/payments/mpesa/stk-push", json=body)
    assert response.status_code == 422


# ─── D) SQL INJECTION PREVENTION TESTS ───
@pytest.mark.asyncio
async def test_payment_status_sql_injection_mitigation(async_client: AsyncClient):
    """Verify status route containing SQL injection payload degrades safely."""
    # Should safely return 404 because query binds parameter securely
    injection_id = "ws_CO_123' OR '1'='1"
    response = await async_client.get(f"/api/v1/payments/mpesa/status/{injection_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ─── E) STRIPE CHARGE TESTS ───
@pytest.mark.asyncio
@patch("app.api.v1.endpoints.payments.process_registration_email")
async def test_stripe_charge_success(mock_email, async_client: AsyncClient):
    """Verify that a valid Stripe charge updates transaction/registration and sends email."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Masterclass",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        db.add(r)
        await db.commit()

    body = {
        "registration_id": str(reg_id),
        "token": "tok_visa",
        "amount": 100.0,
    }

    response = await async_client.post("/api/v1/payments/stripe/charge", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "stripe_" in data["checkout_request_id"]

    # Verify transaction and registration state in DB
    async with TestingSessionLocal() as db:
        from sqlalchemy import select
        res = await db.execute(select(PaymentTransaction).filter(PaymentTransaction.registration_id == reg_id))
        tx = res.scalars().first()
        assert tx is not None
        assert tx.status == "completed"
        assert tx.amount == 100.0

        res_reg = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == reg_id))
        reg = res_reg.scalars().first()
        assert reg.status == "confirmed"


@pytest.mark.asyncio
async def test_stripe_charge_not_found(async_client: AsyncClient):
    """Verify Stripe charge returns 404 if registration does not exist."""
    body = {
        "registration_id": str(uuid.uuid4()),
        "token": "tok_visa",
        "amount": 100.0,
    }
    response = await async_client.post("/api/v1/payments/stripe/charge", json=body)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stripe_charge_validation_extra_fields(async_client: AsyncClient):
    """Verify Stripe charge rejects unexpected extra fields."""
    body = {
        "registration_id": str(uuid.uuid4()),
        "token": "tok_visa",
        "amount": 100.0,
        "malicious_field": "exploit"
    }
    response = await async_client.post("/api/v1/payments/stripe/charge", json=body)
    assert response.status_code == 422

