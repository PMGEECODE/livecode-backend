from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.limiter import limiter
from app.db.models.newsletter import NewsletterSubscriber
from app.schemas.newsletter import NewsletterSubscribe, NewsletterSubscriberResponse
from app.services.newsletter_worker import new_unsubscribe_token, queue_delivery, digest_email, trigger_newsletter_worker

router = APIRouter()


@router.post("/subscribe", response_model=NewsletterSubscriberResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def subscribe_newsletter(
    request: Request,
    response: Response,
    payload: NewsletterSubscribe,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    email = str(payload.email).lower()
    existing = (await db.execute(
        select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)
    )).scalars().first()

    if existing:
        existing.full_name = payload.full_name
        existing.phone = payload.phone
        existing.occupation = payload.occupation
        existing.source = payload.source
        existing.is_active = True
        existing.unsubscribed_at = None
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        background_tasks.add_task(trigger_newsletter_worker)
        return existing

    subscriber = NewsletterSubscriber(
        full_name=payload.full_name,
        email=email,
        phone=payload.phone,
        occupation=payload.occupation,
        source=payload.source,
        unsubscribe_token=new_unsubscribe_token(),
    )
    db.add(subscriber)
    await db.commit()
    await db.refresh(subscriber)
    background_tasks.add_task(trigger_newsletter_worker)
    return subscriber


@router.get("/unsubscribe/{token}")
async def unsubscribe_newsletter(token: str, db: AsyncSession = Depends(deps.get_db)) -> dict:
    subscriber = (await db.execute(
        select(NewsletterSubscriber).where(NewsletterSubscriber.unsubscribe_token == token)
    )).scalars().first()
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    subscriber.is_active = False
    subscriber.unsubscribed_at = datetime.now(timezone.utc)
    db.add(subscriber)
    await db.commit()
    return {"message": "You have been unsubscribed from Livecode Technologies newsletters."}


@router.get("/subscribers", response_model=List[NewsletterSubscriberResponse])
async def list_newsletter_subscribers(
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.get_current_active_superuser),
) -> Any:
    result = await db.execute(select(NewsletterSubscriber).order_by(NewsletterSubscriber.created_at.desc()).limit(500))
    return result.scalars().all()


@router.post("/dispatch", status_code=status.HTTP_202_ACCEPTED)
async def dispatch_newsletter_manually(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.get_current_active_superuser),
) -> dict:
    """Manually dispatch the weekly digest newsletter to all active subscribers."""
    now = datetime.now(timezone.utc)
    result = await db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.is_active == True))  # noqa: E712
    subscribers = result.scalars().all()
    count = 0
    for subscriber in subscribers:
        subject, html_body = digest_email(subscriber)
        await queue_delivery(db, subscriber, subject, html_body)
        subscriber.last_digest_sent_at = now
        count += 1
    await db.commit()
    background_tasks.add_task(trigger_newsletter_worker)
    return {"message": f"Successfully queued newsletter dispatch to {count} active subscribers."}
