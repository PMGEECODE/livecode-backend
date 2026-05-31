import pytest
import pytest_asyncio
import uuid
from typing import AsyncGenerator
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from unittest.mock import patch, AsyncMock

from app.main import app
from app.api.deps import get_db
from app.db.base import Base
from app.db.models.registration import CourseRegistration
from app.db.models.payment import PaymentTransaction
from app.db.models.course import Course, CourseLogistics
from app.services.mpesa import mpesa_service

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_payments_db.sqlite"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)

async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Initializes schema and tables before every test in an isolated session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    yield
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]


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
@patch("app.services.paystack.PaystackService.initialize_transaction")
async def test_paystack_initialize_uses_backend_amount(mock_initialize, async_client: AsyncClient):
    course_id = uuid.uuid4()
    reg_id = uuid.uuid4()

    async with TestingSessionLocal() as db:
        course = Course(
            id=course_id,
            title="Secure Payments",
            slug="secure-payments",
            category="Technology",
        )
        logistics = CourseLogistics(
            course_id=course_id,
            price_usd=100.0,
            price_kes=13000.0,
        )
        registration = CourseRegistration(
            id=reg_id,
            course_id=course_id,
            course_title="Secure Payments",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            currency="USD",
            status="pending",
        )
        db.add_all([course, logistics, registration])
        await db.commit()

    mock_initialize.return_value = {
        "authorization_url": "https://checkout.paystack.test/pay/ref",
        "access_code": "access_123",
        "reference": "ignored",
    }

    response = await async_client.post(
        "/api/v1/payments/paystack/initialize",
        json={"registration_id": str(reg_id)},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["authorization_url"] == "https://checkout.paystack.test/pay/ref"
    assert data["amount"] == 116.0
    assert data["currency"] == "USD"

    call_kwargs = mock_initialize.call_args.kwargs
    assert call_kwargs["amount"] == 116.0
    assert call_kwargs["currency"] == "USD"
    assert call_kwargs["email"] == "jane@example.com"

    async with TestingSessionLocal() as db:
        tx_res = await db.execute(select(PaymentTransaction))
        tx = tx_res.scalars().first()
        assert tx is not None
        assert tx.provider == "paystack"
        assert tx.status == "pending"
        assert tx.amount == 116.0


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.payment_modules.paystack.process_registration_email")
@patch("app.services.paystack.PaystackService.verify_transaction")
async def test_paystack_status_verifies_and_confirms_registration(mock_verify, mock_email, async_client: AsyncClient):
    course_id = uuid.uuid4()
    reg_id = uuid.uuid4()
    reference = "psk_test_reference"

    async with TestingSessionLocal() as db:
        course = Course(
            id=course_id,
            title="Secure Payments",
            slug="secure-payments-verify",
            category="Technology",
        )
        logistics = CourseLogistics(
            course_id=course_id,
            price_usd=100.0,
        )
        registration = CourseRegistration(
            id=reg_id,
            course_id=course_id,
            course_title="Secure Payments",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            currency="USD",
            status="pending",
        )
        transaction = PaymentTransaction(
            registration_id=reg_id,
            checkout_request_id=reference,
            amount=116.0,
            phone_number="Paystack",
            provider="paystack",
            provider_reference=reference,
            currency="USD",
            status="pending",
        )
        db.add_all([course, logistics, registration, transaction])
        await db.commit()

    mock_verify.return_value = {
        "status": "success",
        "reference": reference,
        "amount": 11600,
        "currency": "USD",
        "id": "paystack_receipt_123",
        "paid_at": "2026-05-31T12:00:00.000Z",
    }

    response = await async_client.get(f"/api/v1/payments/paystack/status/{reference}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "completed"
    assert data["receipt_number"] == "paystack_receipt_123"

    async with TestingSessionLocal() as db:
        reg_res = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == reg_id))
        registration = reg_res.scalars().first()
        assert registration.status == "confirmed"

        tx_res = await db.execute(select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == reference))
        tx = tx_res.scalars().first()
        assert tx.status == "completed"
        assert tx.result_code == "0"


@pytest.mark.asyncio
@patch("app.core.config.settings.PUBLIC_SITE_URL", "https://livecodetechnologies.com")
@patch("app.core.config.settings.PAYSTACK_FRONTEND_RETURN_URL", "https://livecodetechnologies.com")
@patch("app.api.v1.endpoints.payment_modules.paystack.process_registration_email")
@patch("app.services.paystack.PaystackService.verify_transaction")
async def test_paystack_callback_redirects_to_registration_success_page(mock_verify, mock_email, async_client: AsyncClient):
    course_id = uuid.uuid4()
    reg_id = uuid.uuid4()
    reference = "psk_callback_reference"

    async with TestingSessionLocal() as db:
        course = Course(
            id=course_id,
            title="Secure Payments",
            slug="secure-payments-callback",
            category="Technology",
        )
        logistics = CourseLogistics(
            course_id=course_id,
            price_usd=100.0,
        )
        registration = CourseRegistration(
            id=reg_id,
            course_id=course_id,
            course_title="Secure Payments",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            currency="USD",
            status="pending",
        )
        transaction = PaymentTransaction(
            registration_id=reg_id,
            checkout_request_id=reference,
            amount=116.0,
            phone_number="Paystack",
            provider="paystack",
            provider_reference=reference,
            currency="USD",
            status="pending",
        )
        db.add_all([course, logistics, registration, transaction])
        await db.commit()

    mock_verify.return_value = {
        "status": "success",
        "reference": reference,
        "amount": 11600,
        "currency": "USD",
        "id": "paystack_receipt_456",
        "paid_at": "2026-05-31T12:00:00.000Z",
    }

    response = await async_client.get(
        f"/api/v1/payments/paystack/callback?reference={reference}",
        follow_redirects=False,
    )

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == (
        "https://livecodetechnologies.com/trainings/secure-payments-callback/register"
        f"?payment_provider=paystack&payment_status=success&reference={reference}&registration_id={reg_id}"
    )


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.payment_modules.mpesa.process_registration_email")
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
@patch("app.api.v1.endpoints.payment_modules.stripe.process_registration_email")
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
        "number": "4242424242424242",
        "exp_month": "12",
        "exp_year": "2030",
        "cvc": "123",
        "amount": 100.0,
        "currency": "usd"
    }

    # Patch stripe methods
    with patch("stripe.Token.create") as mock_token, \
         patch("stripe.Charge.create") as mock_charge:
        mock_token.return_value.id = "tok_test123"
        mock_charge.return_value.status = "succeeded"
        mock_charge.return_value.id = "ch_test123"
        mock_charge.return_value.receipt_url = "https://receipt.stripe.com/123"

        response = await async_client.post("/api/v1/payments/stripe/charge", json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify db update
    async with TestingSessionLocal() as db:
        from sqlalchemy import select
        res = await db.execute(select(CourseRegistration).filter(CourseRegistration.id == reg_id))
        reg = res.scalars().first()
        assert reg.status == "confirmed"

        tx_res = await db.execute(select(PaymentTransaction).filter(PaymentTransaction.registration_id == reg_id))
        tx = tx_res.scalars().first()
        assert tx is not None
        assert tx.status == "completed"

    mock_email.assert_called_once()

@pytest.mark.asyncio
async def test_stripe_charge_not_found(async_client: AsyncClient):
    """Verify Stripe charge returns 404 if registration does not exist."""
    body = {
        "registration_id": str(uuid.uuid4()),
        "number": "4242424242424242",
        "exp_month": "12",
        "exp_year": "2030",
        "cvc": "123",
        "amount": 100.0,
        "currency": "usd"
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


@pytest.mark.asyncio
async def test_stripe_charge_idempotent(async_client: AsyncClient):
    """Verify that attempting to charge an already confirmed registration returns success immediately without creating new charges."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Masterclass",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="confirmed",  # Already paid/confirmed
        )
        db.add(r)
        await db.commit()

    body = {
        "registration_id": str(reg_id),
        "number": "4242424242424242",
        "exp_month": "12",
        "exp_year": "2030",
        "cvc": "123",
        "amount": 100.0,
        "currency": "usd"
    }

    response = await async_client.post("/api/v1/payments/stripe/charge", json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "duplicate_" in response.json()["checkout_request_id"]


@pytest.mark.asyncio
async def test_initiate_stk_push_already_confirmed(async_client: AsyncClient):
    """Verify that initiating STK Push for an already paid registration is rejected."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Masterclass",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="confirmed",
        )
        db.add(r)
        await db.commit()

    body = {
        "registration_id": str(reg_id),
        "phone_number": "0712345678",
        "amount": 100.0
    }
    response = await async_client.post("/api/v1/payments/mpesa/stk-push", json=body)
    assert response.status_code == 400
    assert "already been paid" in response.json()["detail"]


@pytest.mark.asyncio
async def test_initiate_stk_push_deduplication(async_client: AsyncClient):
    """Verify that concurrent or close consecutive STK push requests return the existing pending checkout ID."""
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
        t = PaymentTransaction(
            registration_id=reg_id,
            checkout_request_id="ws_CO_existing123",
            merchant_request_id="merch_123",
            amount=100.0,
            phone_number="254712345678",
            status="pending",
        )
        db.add_all([r, t])
        await db.commit()

    body = {
        "registration_id": str(reg_id),
        "phone_number": "0712345678",
        "amount": 100.0
    }
    response = await async_client.post("/api/v1/payments/mpesa/stk-push", json=body)
    assert response.status_code == 201
    data = response.json()
    assert data["checkout_request_id"] == "ws_CO_existing123"
    assert "already processing" in data["customer_message"]


# ─── F) PAYPAL GATEWAY TESTS ───

@pytest.mark.asyncio
@patch("app.core.config.settings.PAYPAL_CLIENT_ID", "mock_client_id")
async def test_paypal_config_route(async_client: AsyncClient):
    """Verify PayPal config endpoint returns client ID and mode correctly."""
    response = await async_client.get("/api/v1/payments/paypal/config")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["client_id"] == "mock_client_id"
    assert data["mode"] in ("sandbox", "live")


@pytest.mark.asyncio
@patch("app.services.paypal.PayPalService.create_order")
async def test_paypal_create_order_success(mock_create, async_client: AsyncClient):
    """Verify that create-order calls PayPal API and logs transaction as pending."""
    reg_id = uuid.uuid4()
    course_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        # Seed course and logistics for total calculation
        from app.db.models.course import Course, CourseLogistics
        c = Course(id=course_id, title="FastAPI Course", slug="fastapi-course", category="IT")
        log = CourseLogistics(course_id=course_id, price_usd=100.0)
        r = CourseRegistration(
            id=reg_id,
            course_id=course_id,
            course_title="FastAPI Course",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
            currency="USD",
        )
        db.add_all([c, log, r])
        await db.commit()

    mock_create.return_value = {"id": "paypal_order_123"}

    body = {"registration_id": str(reg_id)}
    response = await async_client.post("/api/v1/payments/paypal/create-order", json=body)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"order_id": "paypal_order_123"}

    # Verify transaction in db
    async with TestingSessionLocal() as db:
        res = await db.execute(select(PaymentTransaction).filter(PaymentTransaction.registration_id == reg_id))
        tx = res.scalars().first()
        assert tx is not None
        assert tx.checkout_request_id == "paypal_paypal_order_123"
        assert tx.status == "pending"


@pytest.mark.asyncio
async def test_paypal_create_order_already_confirmed(async_client: AsyncClient):
    """Verify create-order rejects already paid/confirmed registrations."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Course",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="confirmed",
        )
        db.add(r)
        await db.commit()

    body = {"registration_id": str(reg_id)}
    response = await async_client.post("/api/v1/payments/paypal/create-order", json=body)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.payment_modules.paypal.process_registration_email")
@patch("app.services.paypal.PayPalService.capture_order")
async def test_paypal_capture_order_success(mock_capture, mock_email, async_client: AsyncClient):
    """Verify capturing order updates statuses and triggers email confirmation."""
    reg_id = uuid.uuid4()
    order_id = "order_abc"
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Course",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        t = PaymentTransaction(
            registration_id=reg_id,
            checkout_request_id=f"paypal_{order_id}",
            merchant_request_id=f"paypal_order_{order_id}",
            amount=116.0,
            phone_number="PayPal",
            status="pending",
        )
        db.add_all([r, t])
        await db.commit()

    mock_capture.return_value = {
        "id": order_id,
        "status": "COMPLETED",
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {"id": "capture_xyz", "status": "COMPLETED"}
                    ]
                }
            }
        ]
    }

    body = {"registration_id": str(reg_id), "order_id": order_id}
    response = await async_client.post("/api/v1/payments/paypal/capture-order", json=body)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "success"

    # Verify db status updates
    async with TestingSessionLocal() as db:
        r_db = (await db.execute(select(CourseRegistration).filter(CourseRegistration.id == reg_id))).scalars().first()
        assert r_db.status == "confirmed"

        t_db = (await db.execute(select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == f"paypal_{order_id}"))).scalars().first()
        assert t_db.status == "completed"
        assert t_db.mpesa_receipt_number == "capture_xyz"

    mock_email.assert_called_once()


@pytest.mark.asyncio
async def test_paypal_capture_order_idempotent(async_client: AsyncClient):
    """Verify capture route is idempotent if registration is already confirmed."""
    reg_id = uuid.uuid4()
    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Course",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="confirmed",
        )
        db.add(r)
        await db.commit()

    body = {"registration_id": str(reg_id), "order_id": "any_order"}
    response = await async_client.post("/api/v1/payments/paypal/capture-order", json=body)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_paypal_validation_extra_fields(async_client: AsyncClient):
    """Verify PayPal requests reject unexpected parameters to prevent injection."""
    body_create = {
        "registration_id": str(uuid.uuid4()),
        "extra_field": "not_allowed"
    }
    res_create = await async_client.post("/api/v1/payments/paypal/create-order", json=body_create)
    assert res_create.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    body_capture = {
        "registration_id": str(uuid.uuid4()),
        "order_id": "order_123",
        "hacked_amount": 0.01
    }
    res_capture = await async_client.post("/api/v1/payments/paypal/capture-order", json=body_capture)
    assert res_capture.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_paypal_sql_injection_mitigation(async_client: AsyncClient):
    """Verify PayPal endpoints degrade safely under SQL injection payloads."""
    body = {
        "registration_id": str(uuid.uuid4()),
        "order_id": "order' OR '1'='1"
    }
    response = await async_client.post("/api/v1/payments/paypal/capture-order", json=body)
    # Registration ID won't exist, should safely raise 404 rather than SQL syntax error or data compromise
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.payment_modules.paypal.process_registration_email")
@patch("app.api.v1.endpoints.payment_modules.paypal.paypal_service.verify_webhook_signature")
async def test_paypal_webhook_success(mock_verify, mock_email, async_client: AsyncClient):
    """Verify that PAYMENT.CAPTURE.COMPLETED webhook confirms registration."""
    mock_verify.return_value = True
    reg_id = uuid.uuid4()
    order_id = "webhook_order_123"

    async with TestingSessionLocal() as db:
        r = CourseRegistration(
            id=reg_id,
            course_title="FastAPI Course",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            registration_type="individual",
            status="pending",
        )
        t = PaymentTransaction(
            registration_id=reg_id,
            checkout_request_id=f"paypal_{order_id}",
            merchant_request_id=f"paypal_order_{order_id}",
            amount=100.0,
            phone_number="PayPal",
            status="pending",
        )
        db.add_all([r, t])
        await db.commit()

    webhook_payload = {
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "capture_webhook_789",
            "links": [
                {
                    "href": f"https://api.sandbox.paypal.com/v2/checkout/orders/{order_id}",
                    "rel": "up"
                }
            ]
        }
    }

    # Set mock webhook id to allow signature check
    with patch("app.core.config.settings.PAYPAL_WEBHOOK_ID", "mock_webhook_id"):
        response = await async_client.post(
            "/api/v1/payments/paypal/webhook",
            json=webhook_payload,
            headers={
                "PAYPAL-TRANSMISSION-ID": "tx_123",
                "PAYPAL-TRANSMISSION-TIME": "time_123",
                "PAYPAL-CERT-URL": "cert_url",
                "PAYPAL-AUTH-ALGO": "algo",
                "PAYPAL-TRANSMISSION-SIG": "sig"
            }
        )
    assert response.status_code == status.HTTP_200_OK

    # Check database confirmed
    async with TestingSessionLocal() as db:
        r_db = (await db.execute(select(CourseRegistration).filter(CourseRegistration.id == reg_id))).scalars().first()
        assert r_db.status == "confirmed"

        t_db = (await db.execute(select(PaymentTransaction).filter(PaymentTransaction.checkout_request_id == f"paypal_{order_id}"))).scalars().first()
        assert t_db.status == "completed"
        assert t_db.mpesa_receipt_number == "capture_webhook_789"
