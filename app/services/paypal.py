import logging
import base64
import time
from typing import Dict, Any, Optional
import httpx
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)


class PayPalService:
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def base_url(self) -> str:
        if settings.PAYPAL_MODE == "live":
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"

    async def get_access_token(self) -> str:
        """
        Retrieves a valid OAuth2 access token for PayPal.
        Caches it until near expiration to avoid redundant calls.
        """
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
            logger.error("PayPal client credentials are not configured.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="PayPal payment gateway credentials are not configured on the server.",
            )

        auth_str = f"{settings.PAYPAL_CLIENT_ID}:{settings.PAYPAL_CLIENT_SECRET}"
        auth_bytes = auth_str.encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")

        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    headers=headers,
                    data=data,
                )
                response.raise_for_status()
                res_data = response.json()
            except httpx.HTTPError as e:
                logger.error(f"Failed to authenticate with PayPal: {e}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to authenticate with PayPal payment gateway.",
                )

        self._access_token = res_data["access_token"]
        # token expires_in is usually 32400 seconds (9 hours)
        self._token_expires_at = now + float(res_data.get("expires_in", 32400))
        return self._access_token

    async def create_order(
        self, registration_id: str, amount_usd: float, description: str
    ) -> Dict[str, Any]:
        """
        Create a PayPal order for capture.
        """
        token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": str(registration_id),
                    "amount": {
                        "currency_code": "USD",
                        "value": f"{amount_usd:.2f}",
                    },
                    "description": description,
                }
            ],
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v2/checkout/orders",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"PayPal order creation failed: {e}")
                if e.response is not None:
                    logger.error(f"PayPal Error details: {e.response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to create order with PayPal.",
                )

    async def capture_order(self, order_id: str) -> Dict[str, Any]:
        """
        Capture a PayPal order.
        """
        token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                    headers=headers,
                    json={},
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"PayPal order capture failed for ID {order_id}: {e}")
                if e.response is not None:
                    logger.error(f"PayPal Error details: {e.response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to capture payment with PayPal.",
                )

    async def verify_webhook_signature(
        self,
        request_headers: Dict[str, str],
        webhook_body: bytes,
        webhook_id: str,
    ) -> bool:
        """
        Verify signature of PayPal webhook notification.
        """
        token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Extracts PayPal headers safely
        payload = {
            "transmission_id": request_headers.get("PAYPAL-TRANSMISSION-ID"),
            "transmission_time": request_headers.get("PAYPAL-TRANSMISSION-TIME"),
            "cert_url": request_headers.get("PAYPAL-CERT-URL"),
            "auth_algo": request_headers.get("PAYPAL-AUTH-ALGO"),
            "transmission_sig": request_headers.get("PAYPAL-TRANSMISSION-SIG"),
            "webhook_id": webhook_id,
            "webhook_event": httpx.post(  # PayPal needs the event object as JSON
                "https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature"
            ).json() if False else None,  # Will parse below
        }

        # Need the raw body parsed to dict
        import json
        try:
            event = json.loads(webhook_body.decode("utf-8"))
        except Exception:
            return False

        payload["webhook_event"] = event

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/notifications/verify-webhook-signature",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                res_data = response.json()
                return res_data.get("verification_status") == "SUCCESS"
            except httpx.HTTPError as e:
                logger.error(f"PayPal webhook signature verification request failed: {e}")
                return False


paypal_service = PayPalService()
