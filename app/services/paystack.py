import hashlib
import hmac
import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class PaystackService:
    base_url = "https://api.paystack.co"

    @property
    def secret_key(self) -> str:
        key = settings.paystack_secret_key
        if not key:
            logger.error("Paystack secret key is not configured.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Paystack payment gateway is not configured on the server.",
            )
        return key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def initialize_transaction(
        self,
        *,
        email: str,
        amount: float,
        currency: str,
        reference: str,
        callback_url: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        amount_subunit = int(round(amount * 100))
        payload = {
            "email": email,
            "amount": amount_subunit,
            "currency": currency.upper(),
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
            "channels": ["card"],
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/transaction/initialize",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                logger.error("Paystack initialize failed: %s", exc.response.text)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to initialize Paystack payment.",
                )
            except httpx.HTTPError as exc:
                logger.error("Paystack initialize network error: %s", repr(exc))
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Paystack payment gateway is temporarily unavailable.",
                )

        if not data.get("status") or not data.get("data", {}).get("authorization_url"):
            logger.error("Unexpected Paystack initialize response: %s", data)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid response from Paystack payment gateway.",
            )
        return data["data"]

    async def verify_transaction(self, reference: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/transaction/verify/{reference}",
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                logger.error("Paystack verify failed for %s: %s", reference, exc.response.text)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to verify Paystack payment.",
                )
            except httpx.HTTPError as exc:
                logger.error("Paystack verify network error for %s: %s", reference, repr(exc))
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Paystack verification is temporarily unavailable.",
                )

        if not data.get("status"):
            logger.warning("Paystack verification returned unsuccessful status for %s: %s", reference, data)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Paystack could not verify this payment.",
            )
        return data.get("data", {})

    def verify_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        digest = hmac.new(
            self.secret_key.encode("utf-8"),
            raw_body,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(digest, signature)


paystack_service = PaystackService()
