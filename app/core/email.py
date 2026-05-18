import smtplib
from email.message import EmailMessage
import io
import asyncio
from typing import List, Dict, Any, Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

def send_email_sync(to_email: str, subject: str, html_body: str, attachments: Optional[List[Dict[str, Any]]] = None):
    if not settings.SMTP_HOST:
        logger.warning(f"SMTP_HOST not configured. Mock sending email to {to_email} with subject: '{subject}'")
        return

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
    msg['To'] = to_email
    msg.set_content("Please enable HTML to view this email.")
    msg.add_alternative(html_body, subtype='html')

    if attachments:
        for attachment in attachments:
            msg.add_attachment(
                attachment["content"],
                maintype=attachment["maintype"],
                subtype=attachment["subtype"],
                filename=attachment["filename"]
            )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_PORT == 587:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
            logger.info(f"Successfully sent email to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")

async def send_email_async(to_email: str, subject: str, html_body: str, attachments: Optional[List[Dict[str, Any]]] = None):
    await asyncio.to_thread(send_email_sync, to_email, subject, html_body, attachments)
