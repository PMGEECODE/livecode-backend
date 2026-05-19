import base64
from datetime import datetime
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class MpesaService:
    def __init__(self):
        self.env = settings.MPESA_ENVIRONMENT.lower()
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.shortcode = settings.MPESA_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY
        self.callback_url = settings.MPESA_CALLBACK_URL

        # Base URLs for Sandbox / Production
        if self.env == "production":
            self.base_url = "https://api.safaricom.co.ke"
        else:
            self.base_url = "https://sandbox.safaricom.co.ke"

    def format_phone(self, phone: str) -> str:
        """Format phone number to Safaricom standard (2547XXXXXXXX or 2541XXXXXXXX)."""
        clean = "".join(filter(str.isdigit, phone))
        if clean.startswith("0"):
            clean = "254" + clean[1:]
        elif clean.startswith("7") or clean.startswith("1"):
            clean = "254" + clean
        elif clean.startswith("+254"):
            clean = clean[1:]
        elif not clean.startswith("254"):
            clean = "254" + clean
        return clean

    async def get_access_token(self) -> str:
        """Generate access token using Consumer Key and Consumer Secret."""
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(
                    url,
                    auth=(self.consumer_key, self.consumer_secret)
                )
                response.raise_for_status()
                data = response.json()
                return data["access_token"]
            except httpx.HTTPError as exc:
                logger.error(f"HTTP error occurred while generating M-Pesa token: {exc}")
                raise RuntimeError("Failed to generate M-Pesa access token.")

    async def initiate_stk_push(self, phone_number: str, amount: float, account_reference: str) -> dict:
        """Initiate Mpesa STK Push via Daraja API."""
        formatted_phone = self.format_phone(phone_number)
        access_token = await self.get_access_token()
        
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password_str = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(password_str.encode("utf-8")).decode("utf-8")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Safaricom STK Push requires whole integers (KES)
        amt = int(amount)
        if amt < 1:
            amt = 1

        payload = {
            "BusinessShortCode": int(self.shortcode),
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amt,
            "PartyA": int(formatted_phone),
            "PartyB": int(self.shortcode),
            "PhoneNumber": int(formatted_phone),
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference[:12],
            "TransactionDesc": f"Payment for {account_reference[:20]}"
        }

        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                logger.error(f"HTTP error occurred while initiating STK Push: {exc}")
                raise RuntimeError("M-Pesa STK Push request failed.")


mpesa_service = MpesaService()
