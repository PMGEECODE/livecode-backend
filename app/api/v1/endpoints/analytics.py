import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.core.limiter import limiter
from app.db.models.analytics import ProductAnalyticsEvent
from app.schemas.analytics import AnalyticsEventCreate, AnalyticsEventResponse, ALLOWED_ANALYTICS_EVENTS

router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def _hash_ip(ip: str) -> Optional[str]:
    if not ip:
        return None
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode("utf-8")).hexdigest()


@router.post("/track", response_model=AnalyticsEventResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("120/minute")
async def track_analytics_event(
    request: Request,
    response: Response,
    payload: AnalyticsEventCreate,
    db: AsyncSession = Depends(deps.get_db),
) -> ProductAnalyticsEvent:
    event = ProductAnalyticsEvent(
        event_name=payload.event_name,
        page_path=payload.page_path,
        page_title=payload.page_title,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity_title=payload.entity_title,
        referrer=payload.referrer,
        session_id=payload.session_id,
        duration_ms=payload.duration_ms,
        scroll_depth_percent=payload.scroll_depth_percent,
        interaction_count=payload.interaction_count,
        metadata_json=payload.metadata,
        user_agent=(request.headers.get("user-agent") or "")[:800] or None,
        ip_hash=_hash_ip(_client_ip(request)),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("/summary")
async def get_analytics_summary(
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.get_current_active_superuser),
    days: int = 30,
) -> Dict[str, Any]:
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_events = (await db.execute(
        select(func.count(ProductAnalyticsEvent.id)).where(ProductAnalyticsEvent.created_at >= since)
    )).scalar() or 0

    event_rows = (await db.execute(
        select(ProductAnalyticsEvent.event_name, func.count(ProductAnalyticsEvent.id))
        .where(ProductAnalyticsEvent.created_at >= since)
        .group_by(ProductAnalyticsEvent.event_name)
        .order_by(desc(func.count(ProductAnalyticsEvent.id)))
    )).all()

    entity_rows = (await db.execute(
        select(
            ProductAnalyticsEvent.entity_type,
            ProductAnalyticsEvent.entity_id,
            ProductAnalyticsEvent.entity_title,
            func.count(ProductAnalyticsEvent.id),
        )
        .where(ProductAnalyticsEvent.created_at >= since)
        .where(ProductAnalyticsEvent.entity_id.is_not(None))
        .group_by(ProductAnalyticsEvent.entity_type, ProductAnalyticsEvent.entity_id, ProductAnalyticsEvent.entity_title)
        .order_by(desc(func.count(ProductAnalyticsEvent.id)))
        .limit(10)
    )).all()

    page_rows = (await db.execute(
        select(
            ProductAnalyticsEvent.page_path,
            func.count(ProductAnalyticsEvent.id),
            func.count(func.distinct(ProductAnalyticsEvent.session_id)),
            func.avg(ProductAnalyticsEvent.duration_ms),
            func.avg(ProductAnalyticsEvent.scroll_depth_percent),
            func.sum(ProductAnalyticsEvent.interaction_count),
        )
        .where(ProductAnalyticsEvent.created_at >= since)
        .where(ProductAnalyticsEvent.page_path.is_not(None))
        .where(ProductAnalyticsEvent.event_name.in_(["page_view", "page_engagement"]))
        .group_by(ProductAnalyticsEvent.page_path)
        .order_by(desc(func.count(ProductAnalyticsEvent.id)))
        .limit(10)
    )).all()

    recent_events = (await db.execute(
        select(ProductAnalyticsEvent)
        .where(ProductAnalyticsEvent.created_at >= since)
        .order_by(ProductAnalyticsEvent.created_at.desc())
        .limit(25)
    )).scalars().all()

    counts_by_event = {name: count for name, count in event_rows}
    avg_duration_ms = (await db.execute(
        select(func.avg(ProductAnalyticsEvent.duration_ms))
        .where(ProductAnalyticsEvent.created_at >= since)
        .where(ProductAnalyticsEvent.duration_ms.is_not(None))
    )).scalar()
    avg_scroll_depth = (await db.execute(
        select(func.avg(ProductAnalyticsEvent.scroll_depth_percent))
        .where(ProductAnalyticsEvent.created_at >= since)
        .where(ProductAnalyticsEvent.scroll_depth_percent.is_not(None))
    )).scalar()
    total_interactions = (await db.execute(
        select(func.sum(ProductAnalyticsEvent.interaction_count))
        .where(ProductAnalyticsEvent.created_at >= since)
        .where(ProductAnalyticsEvent.interaction_count.is_not(None))
    )).scalar() or 0
    total_sessions = (await db.execute(
        select(func.count(func.distinct(ProductAnalyticsEvent.session_id)))
        .where(ProductAnalyticsEvent.created_at >= since)
        .where(ProductAnalyticsEvent.session_id.is_not(None))
    )).scalar() or 0

    return {
        "days": days,
        "total_events": total_events,
        "total_sessions": total_sessions,
        "avg_duration_seconds": round((float(avg_duration_ms or 0) / 1000), 1),
        "avg_scroll_depth_percent": round(float(avg_scroll_depth or 0), 1),
        "total_interactions": int(total_interactions or 0),
        "events": [
            {"event_name": event_name, "count": counts_by_event.get(event_name, 0)}
            for event_name in sorted(ALLOWED_ANALYTICS_EVENTS)
        ],
        "top_entities": [
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_title": entity_title,
                "count": count,
            }
            for entity_type, entity_id, entity_title, count in entity_rows
        ],
        "top_pages": [
            {
                "page_path": page_path,
                "views": count,
                "sessions": sessions,
                "avg_duration_seconds": round((float(avg_duration_ms or 0) / 1000), 1),
                "avg_scroll_depth_percent": round(float(avg_scroll_depth or 0), 1),
                "interactions": int(interactions or 0),
            }
            for page_path, count, sessions, avg_duration_ms, avg_scroll_depth, interactions in page_rows
        ],
        "recent_events": [
            {
                "id": str(event.id),
                "event_name": event.event_name,
                "page_path": event.page_path,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "entity_title": event.entity_title,
                "duration_ms": event.duration_ms,
                "scroll_depth_percent": event.scroll_depth_percent,
                "interaction_count": event.interaction_count,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in recent_events
        ],
    }
