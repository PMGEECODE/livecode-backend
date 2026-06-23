from datetime import datetime, timezone
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.limiter import limiter
from app.db.models.newsletter import NewsletterSubscriber, NewsletterTheme
from app.db.models.blog import BlogPost
from app.db.models.course import Course
from app.schemas.newsletter import (
    NewsletterSubscribe,
    NewsletterSubscriberResponse,
    NewsletterThemeCreate,
    NewsletterThemeUpdate,
    NewsletterThemeResponse
)
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
    current_user=Depends(deps.check_permission("view_newsletters")),
) -> Any:
    result = await db.execute(select(NewsletterSubscriber).order_by(NewsletterSubscriber.created_at.desc()).limit(500))
    return result.scalars().all()


@router.post("/dispatch", status_code=status.HTTP_202_ACCEPTED)
async def dispatch_newsletter_manually(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.check_permission("manage_newsletters")),
) -> dict:
    """Manually dispatch the weekly digest newsletter to all active subscribers."""
    now = datetime.now(timezone.utc)
    
    # Fetch active theme if any
    theme_dict = None
    theme_result = await db.execute(select(NewsletterTheme).where(NewsletterTheme.is_active == True))
    active_theme = theme_result.scalars().first()
    if active_theme:
        theme_dict = {
            "primary_color": active_theme.primary_color,
            "secondary_color": active_theme.secondary_color,
            "bg_color": active_theme.bg_color,
            "card_bg": active_theme.card_bg,
            "text_color": active_theme.text_color,
            "heading_color": active_theme.heading_color,
            "font_family": active_theme.font_family,
            "template_layout": active_theme.template_layout,
        }

    # Fetch dynamic content for newsletter
    from app.db.models.product import Product
    from app.db.models.service import Service

    blogs_result = await db.execute(select(BlogPost).order_by(BlogPost.published_date.desc()).limit(2))
    blogs = blogs_result.scalars().all()
    courses_result = await db.execute(select(Course).order_by(Course.slug.desc()).limit(2))
    courses = courses_result.scalars().all()
    
    products_result = await db.execute(select(Product).where(Product.is_active == True).limit(2))
    products = products_result.scalars().all()
    
    services_result = await db.execute(select(Service).limit(2))
    services = services_result.scalars().all()

    result = await db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.is_active == True))  # noqa: E712
    subscribers = result.scalars().all()
    count = 0
    for subscriber in subscribers:
        subject, html_body = digest_email(subscriber, blogs, courses, products=products, services=services, theme=theme_dict)
        await queue_delivery(db, subscriber, subject, html_body)
        subscriber.last_digest_sent_at = now
        count += 1
    await db.commit()
    background_tasks.add_task(trigger_newsletter_worker)
    return {"message": f"Successfully queued newsletter dispatch to {count} active subscribers."}


# ─── THEME CRUD ENDPOINTS ───

@router.get("/themes", response_model=List[NewsletterThemeResponse])
async def list_newsletter_themes(
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.check_permission("view_newsletters")),
) -> Any:
    result = await db.execute(select(NewsletterTheme).order_by(NewsletterTheme.name.asc()))
    return result.scalars().all()


@router.post("/themes", response_model=NewsletterThemeResponse, status_code=status.HTTP_201_CREATED)
async def create_newsletter_theme(
    payload: NewsletterThemeCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.check_permission("manage_newsletters")),
) -> Any:
    existing = (await db.execute(
        select(NewsletterTheme).where(NewsletterTheme.name == payload.name)
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Theme name already exists.")

    theme = NewsletterTheme(
        name=payload.name,
        primary_color=payload.primary_color,
        secondary_color=payload.secondary_color,
        bg_color=payload.bg_color,
        card_bg=payload.card_bg,
        text_color=payload.text_color,
        heading_color=payload.heading_color,
        font_family=payload.font_family,
        template_layout=payload.template_layout or "classic_card",
        is_active=False
    )
    db.add(theme)
    await db.commit()
    await db.refresh(theme)
    return theme


@router.put("/themes/{id}", response_model=NewsletterThemeResponse)
async def update_newsletter_theme(
    id: UUID,
    payload: NewsletterThemeUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.check_permission("manage_newsletters")),
) -> Any:
    theme = (await db.execute(
        select(NewsletterTheme).where(NewsletterTheme.id == id)
    )).scalars().first()
    if not theme:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found.")

    if payload.name is not None:
        existing = (await db.execute(
            select(NewsletterTheme).where(NewsletterTheme.name == payload.name, NewsletterTheme.id != id)
        )).scalars().first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Theme name already exists.")
        theme.name = payload.name

    for field in ["primary_color", "secondary_color", "bg_color", "card_bg", "text_color", "heading_color", "font_family", "template_layout"]:
        val = getattr(payload, field, None)
        if val is not None:
            setattr(theme, field, val)

    db.add(theme)
    await db.commit()
    await db.refresh(theme)
    return theme


@router.delete("/themes/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_newsletter_theme(
    id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.check_permission("manage_newsletters")),
) -> None:
    theme = (await db.execute(
        select(NewsletterTheme).where(NewsletterTheme.id == id)
    )).scalars().first()
    if not theme:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found.")
    if theme.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete an active theme.")
    
    await db.delete(theme)
    await db.commit()


@router.post("/themes/{id}/activate", response_model=NewsletterThemeResponse)
async def activate_newsletter_theme(
    id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.check_permission("manage_newsletters")),
) -> Any:
    theme = (await db.execute(
        select(NewsletterTheme).where(NewsletterTheme.id == id)
    )).scalars().first()
    if not theme:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found.")

    await db.execute(
        NewsletterTheme.__table__.update()
        .where(NewsletterTheme.id != id)
        .values(is_active=False)
    )
    theme.is_active = True
    db.add(theme)
    await db.commit()
    await db.refresh(theme)
    return theme
