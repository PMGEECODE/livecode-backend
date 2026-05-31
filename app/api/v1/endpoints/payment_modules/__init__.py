from fastapi import APIRouter

from app.api.v1.endpoints.payment_modules import mpesa, paypal, paystack, stripe

router = APIRouter()
router.include_router(mpesa.router)
router.include_router(stripe.router)
router.include_router(paystack.router)
router.include_router(paypal.router)
