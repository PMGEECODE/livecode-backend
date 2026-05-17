from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.api import deps
from app.db.models.course import Course
from app.db.models.service import Service
from app.db.models.contact import Contact
from app.db.models.registration import CourseRegistration
from app.db.models.blog import BlogPost
from typing import Dict, Any

router = APIRouter()

@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
) -> Dict[str, Any]:
    """
    Retrieve system-wide dashboard statistics including counts for courses,
    services, contact messages, course registrations, blog posts,
    and lists of recent contact messages & registrations.
    """
    # Counts
    courses_count_query = await db.execute(select(func.count(Course.id)))
    courses_count = courses_count_query.scalar() or 0

    services_count_query = await db.execute(select(func.count(Service.id)))
    services_count = services_count_query.scalar() or 0

    total_contacts_query = await db.execute(select(func.count(Contact.id)))
    total_contacts = total_contacts_query.scalar() or 0

    pending_contacts_query = await db.execute(select(func.count(Contact.id)).filter(Contact.is_resolved == False))
    pending_contacts = pending_contacts_query.scalar() or 0

    total_registrations_query = await db.execute(select(func.count(CourseRegistration.id)))
    total_registrations = total_registrations_query.scalar() or 0

    pending_registrations_query = await db.execute(select(func.count(CourseRegistration.id)).filter(CourseRegistration.status == "pending"))
    pending_registrations = pending_registrations_query.scalar() or 0

    blogs_count_query = await db.execute(select(func.count(BlogPost.id)))
    blogs_count = blogs_count_query.scalar() or 0

    # Recent registrations (last 5)
    recent_regs_query = await db.execute(
        select(CourseRegistration)
        .order_by(CourseRegistration.id.desc())
        .limit(5)
    )
    recent_regs = recent_regs_query.scalars().all()
    
    # Recent contacts (last 5)
    recent_contacts_query = await db.execute(
        select(Contact)
        .order_by(Contact.created_at.desc())
        .limit(5)
    )
    recent_contacts = recent_contacts_query.scalars().all()

    return {
        "courses_count": courses_count,
        "services_count": services_count,
        "contacts": {
            "total": total_contacts,
            "pending": pending_contacts,
        },
        "registrations": {
            "total": total_registrations,
            "pending": pending_registrations,
        },
        "blogs_count": blogs_count,
        "recent_registrations": [
            {
                "id": str(r.id),
                "course_title": r.course_title,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "email": r.email,
                "registration_type": r.registration_type,
                "status": r.status,
            }
            for r in recent_regs
        ],
        "recent_contacts": [
            {
                "id": str(c.id),
                "name": c.name,
                "email": c.email,
                "subject": c.subject,
                "is_resolved": c.is_resolved,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_contacts
        ],
    }
