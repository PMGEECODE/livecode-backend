import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy import select

from app.core.config import settings
from app.core.email import send_email_async
from app.db.models.newsletter import NewsletterDelivery, NewsletterSubscriber
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def new_unsubscribe_token() -> str:
    return secrets.token_urlsafe(32)


def _unsubscribe_url(token: str) -> str:
    base = settings.PUBLIC_SITE_URL.strip().rstrip("/")
    return f"{base}/api/v1/newsletter/unsubscribe/{token}" if base else f"/api/v1/newsletter/unsubscribe/{token}"


def welcome_email(subscriber: NewsletterSubscriber) -> tuple[str, str]:
    name = escape(subscriber.full_name)
    unsubscribe_url = _unsubscribe_url(subscriber.unsubscribe_token)
    return (
        "Welcome to Livecode Technologies updates",
        f"""
        <div style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
          <div style="max-width:680px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
            <div style="background:#001A4D;color:#ffffff;padding:22px 24px;">
              <h1 style="margin:0;color:#F49220;font-size:22px;">Welcome, {name}</h1>
              <p style="margin:8px 0 0;color:#dbeafe;font-size:14px;">You are subscribed to Livecode Technologies training and insights.</p>
            </div>
            <div style="padding:24px;color:#334155;font-size:14px;line-height:1.6;">
              <p>We will send you curated updates on upcoming professional trainings, technology insights, and Livecode programs.</p>
              <p style="margin-top:18px;color:#64748b;font-size:12px;">You can unsubscribe at any time: <a href="{unsubscribe_url}">unsubscribe</a>.</p>
            </div>
          </div>
        </div>
        """,
    )


def digest_email(subscriber: NewsletterSubscriber) -> tuple[str, str]:
    unsubscribe_url = _unsubscribe_url(subscriber.unsubscribe_token)
    return (
        "Livecode Technologies weekly training update",
        f"""
        <div style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
          <div style="max-width:680px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
            <div style="background:#001A4D;color:#ffffff;padding:22px 24px;">
              <h1 style="margin:0;color:#F49220;font-size:22px;">Training & Technology Updates</h1>
              <p style="margin:8px 0 0;color:#dbeafe;font-size:14px;">Curated updates from Livecode Technologies.</p>
            </div>
            <div style="padding:24px;color:#334155;font-size:14px;line-height:1.6;">
              <p>Hello {escape(subscriber.full_name)},</p>
              <p>Explore our latest training calendar, course registration opportunities, technology products, and professional development resources on the Livecode Technologies website.</p>
              <p style="margin:20px 0;">
                <a href="https://livecodetechnologies.com/training-calendar" style="background:#F49220;color:white;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:700;">View Training Calendar</a>
              </p>
              <p style="margin-top:18px;color:#64748b;font-size:12px;">You can unsubscribe at any time: <a href="{unsubscribe_url}">unsubscribe</a>.</p>
            </div>
          </div>
        </div>
        """,
    )


async def queue_delivery(db, subscriber: NewsletterSubscriber, subject: str, html_body: str) -> None:
    db.add(NewsletterDelivery(
        subscriber_email=subscriber.email,
        subject=subject,
        html_body=html_body,
        status="pending",
    ))


async def prepare_newsletter_deliveries() -> None:
    now = datetime.now(timezone.utc)
    digest_cutoff = now - timedelta(days=max(1, settings.NEWSLETTER_DIGEST_INTERVAL_DAYS))

    async with SessionLocal() as db:
      result = await db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.is_active == True))  # noqa: E712
      subscribers = result.scalars().all()
      for subscriber in subscribers:
          if not subscriber.welcome_email_sent:
              subject, html_body = welcome_email(subscriber)
              await queue_delivery(db, subscriber, subject, html_body)
              subscriber.welcome_email_sent = True
          elif subscriber.last_digest_sent_at is None or subscriber.last_digest_sent_at <= digest_cutoff:
              subject, html_body = digest_email(subscriber)
              await queue_delivery(db, subscriber, subject, html_body)
              subscriber.last_digest_sent_at = now
      await db.commit()


async def send_pending_deliveries(limit: int = 25) -> None:
    async with SessionLocal() as db:
        result = await db.execute(
            select(NewsletterDelivery)
            .where(NewsletterDelivery.status.in_(["pending", "failed"]))
            .where(NewsletterDelivery.attempts < 3)
            .order_by(NewsletterDelivery.scheduled_at.asc())
            .limit(limit)
        )
        deliveries = result.scalars().all()
        for delivery in deliveries:
            try:
                await send_email_async(delivery.subscriber_email, delivery.subject, delivery.html_body)
                delivery.status = "sent"
                delivery.sent_at = datetime.now(timezone.utc)
                delivery.error_message = None
            except Exception as exc:
                delivery.status = "failed"
                delivery.error_message = str(exc)[:1000]
            finally:
                delivery.attempts = int(delivery.attempts or 0) + 1
        await db.commit()


async def newsletter_worker(stop_event: asyncio.Event) -> None:
    logger.info("Newsletter worker started.")
    while not stop_event.is_set():
        try:
            await prepare_newsletter_deliveries()
            await send_pending_deliveries()
        except Exception as exc:
            logger.error("Newsletter worker cycle failed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(30, settings.NEWSLETTER_WORKER_INTERVAL_SECONDS))
        except asyncio.TimeoutError:
            pass
    logger.info("Newsletter worker stopped.")
