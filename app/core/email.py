import smtplib
import asyncio
from email.utils import formatdate, make_msgid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Any, Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email_sync(
    to_email: str,
    subject: str,
    html_body: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if not settings.SMTP_HOST:
        logger.warning(
            "SMTP_HOST not configured. Email to '%s' with subject '%s' was not sent.",
            to_email,
            subject,
        )
        return

    # Build a multipart/mixed message so attachments are always delivered correctly
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=settings.EMAILS_FROM_EMAIL.split("@")[-1])
    msg["Reply-To"] = settings.EMAILS_FROM_EMAIL

    # Wrap the body in multipart/alternative so plain-text fallback works
    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText("Please enable HTML to view this email.", "plain", "utf-8"))
    body_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(body_part)

    # Attach each file explicitly
    for attachment in (attachments or []):
        mime_base = MIMEBase(attachment["maintype"], attachment["subtype"])
        mime_base.set_payload(attachment["content"])
        encoders.encode_base64(mime_base)
        mime_base.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment["filename"],
        )
        msg.attach(mime_base)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.ehlo()
            if settings.SMTP_PORT == 587:
                server.starttls()
                server.ehlo()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAILS_FROM_EMAIL, [to_email], msg.as_string())
            logger.info("Email sent to %s", to_email)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)


async def send_email_async(
    to_email: str,
    subject: str,
    html_body: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> None:
    await asyncio.to_thread(send_email_sync, to_email, subject, html_body, attachments)
