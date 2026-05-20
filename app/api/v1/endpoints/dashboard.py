import json
from typing import Dict, Any

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api import deps
from app.core.redis import redis_manager
from app.db.models.course import Course
from app.db.models.service import Service
from app.db.models.contact import Contact
from app.db.models.registration import CourseRegistration
from app.db.models.blog import BlogPost

router = APIRouter()

# Cache key and TTL for dashboard stats — 60 s is acceptable staleness for an
# admin overview page and avoids hammering the DB on every panel refresh.
_STATS_CACHE_KEY = "dashboard:stats"
_STATS_CACHE_TTL = 60


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(deps.get_db),
    current_user=Depends(deps.get_current_active_superuser),
) -> Dict[str, Any]:
    """
    Retrieve system-wide dashboard statistics.

    Results are cached in Redis for 60 seconds. The cache is invalidated
    whenever a write endpoint calls redis_manager.delete_pattern('dashboard:*').
    """
    # ── Cache hit ──────────────────────────────────────────────────────────────
    cached = await redis_manager.get(_STATS_CACHE_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass  # corrupt entry — fall through and re-query

    # ── DB queries (sequential on one session; results are rare-changing) ──────
    def _scalar(result) -> int:
        return result.scalar() or 0

    courses_count      = _scalar(await db.execute(select(func.count(Course.id))))
    services_count     = _scalar(await db.execute(select(func.count(Service.id))))
    total_contacts     = _scalar(await db.execute(select(func.count(Contact.id))))
    pending_contacts   = _scalar(await db.execute(
        select(func.count(Contact.id)).filter(Contact.is_resolved == False)  # noqa: E712
    ))
    total_regs         = _scalar(await db.execute(select(func.count(CourseRegistration.id))))
    pending_regs       = _scalar(await db.execute(
        select(func.count(CourseRegistration.id)).filter(CourseRegistration.status == "pending")
    ))
    blogs_count        = _scalar(await db.execute(select(func.count(BlogPost.id))))

    recent_regs_result = await db.execute(
        select(CourseRegistration).order_by(CourseRegistration.id.desc()).limit(5)
    )
    recent_contacts_result = await db.execute(
        select(Contact).order_by(Contact.created_at.desc()).limit(5)
    )

    recent_regs     = recent_regs_result.scalars().all()
    recent_contacts = recent_contacts_result.scalars().all()

    payload: Dict[str, Any] = {
        "courses_count":  courses_count,
        "services_count": services_count,
        "contacts": {
            "total":   total_contacts,
            "pending": pending_contacts,
        },
        "registrations": {
            "total":   total_regs,
            "pending": pending_regs,
        },
        "blogs_count": blogs_count,
        "recent_registrations": [
            {
                "id":                str(r.id),
                "course_title":      r.course_title,
                "first_name":        r.first_name,
                "last_name":         r.last_name,
                "email":             r.email,
                "registration_type": r.registration_type,
                "status":            r.status,
            }
            for r in recent_regs
        ],
        "recent_contacts": [
            {
                "id":         str(c.id),
                "name":       c.name,
                "email":      c.email,
                "subject":    c.subject,
                "is_resolved": c.is_resolved,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_contacts
        ],
    }

    # ── Populate cache ─────────────────────────────────────────────────────────
    await redis_manager.set(
        _STATS_CACHE_KEY,
        json.dumps(jsonable_encoder(payload)),
        expire=_STATS_CACHE_TTL,
    )

    return payload
