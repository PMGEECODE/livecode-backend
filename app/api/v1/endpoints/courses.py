import json
from typing import Any, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app import crud, schemas, models
from app.api import deps
from app.core.sse import sse_manager
from app.core.redis import redis_manager
from app.core.limiter import limiter

router = APIRouter()

@router.get("/", response_model=List[Union[schemas.Course, schemas.CourseSummary]])
@limiter.limit("60/minute")
async def read_courses(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    sub_category: Optional[str] = None,
    search: Optional[str] = None,
    random: bool = False,
    summary: bool = False,
    active_only: bool = False,
) -> Any:
    """
    Retrieve courses. Pass random=true to get a randomised sample (skips cache).
    """
    if not random:
        cache_key = (
            "courses:list:"
            f"skip={skip}:limit={limit}:category={category or ''}:sub_category={sub_category or ''}:search={search or ''}:summary={summary}:active_only={active_only}"
        )
        cached_data = await redis_manager.get(cache_key)
        if cached_data:
            try:
                parsed = json.loads(cached_data)
                response.headers["X-Total-Count"] = str(parsed["total_count"])
                return parsed["items"]
            except Exception:
                pass

    courses = await crud.course.get_multi(
        db,
        skip=skip,
        limit=limit,
        category=category,
        sub_category=sub_category,
        search=search,
        random=random,
        summary=summary,
        active_only=active_only,
    )

    total_count = await crud.course.count_multi(
        db,
        category=category,
        sub_category=sub_category,
        search=search,
        active_only=active_only,
    )

    response.headers["X-Total-Count"] = str(total_count)

    if not random:
        try:
            cache_payload = {
                "items": jsonable_encoder(courses),
                "total_count": total_count
            }
            await redis_manager.set(
                cache_key,
                json.dumps(cache_payload),
                expire=3600
            )
        except Exception:
            pass

    return courses

@router.post("/", response_model=schemas.Course)
async def create_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("manage_courses")),
    course_in: schemas.CourseCreate,
) -> Any:
    """
    Create new course.
    """
    course = await crud.course.get_by_slug(db, slug=course_in.slug)
    if course:
        raise HTTPException(
            status_code=400,
            detail="The course with this slug already exists in the system.",
        )
    new_course = await crud.course.create(db, obj_in=course_in)
    
    # Invalidate cached catalogs, details, and dashboard stats
    await redis_manager.delete_pattern("courses:*")
    await redis_manager.delete_pattern("dashboard:*")
    
    await sse_manager.broadcast("courses_updated", {"action": "create", "id": str(new_course.id)})
    await sse_manager.broadcast("draft_deleted", {"user_id": str(current_user.id), "reason": "publish"})
    return new_course

@router.get("/draft", response_model=Optional[dict])
async def get_course_draft(
    current_user: models.User = Depends(deps.check_permission("view_courses")),
) -> Any:
    """
    Retrieve the current logged-in user's course builder draft from Redis.
    """
    cache_key = f"course_draft:{current_user.id}"
    cached_data = await redis_manager.get(cache_key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except Exception:
            pass
    return None

@router.put("/draft")
async def save_course_draft(
    draft_data: dict,
    current_user: models.User = Depends(deps.check_permission("view_courses")),
) -> Any:
    """
    Save/sync the current user's course builder draft to Redis.
    """
    cache_key = f"course_draft:{current_user.id}"
    # Keep the draft for 30 days (2592000 seconds)
    success = await redis_manager.set(cache_key, json.dumps(draft_data), expire=2592000)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to save course draft on server"
        )
    await sse_manager.broadcast("draft_updated", {"user_id": str(current_user.id)})
    return {"status": "success"}

@router.delete("/draft")
async def delete_course_draft(
    current_user: models.User = Depends(deps.check_permission("view_courses")),
) -> Any:
    """
    Delete/clear the current user's course builder draft from Redis.
    """
    cache_key = f"course_draft:{current_user.id}"
    await redis_manager.delete(cache_key)
    await sse_manager.broadcast("draft_deleted", {"user_id": str(current_user.id), "reason": "discard"})
    return {"status": "success"}


# ---------------------------------------------------------------------------
# Training Calendar endpoint — optimised for the public calendar page.
# Fetches up to 1000 courses with only schedule + logistics data (no blocks).
# All time-based / client-side filtering is done in the browser.
# Redis TTL: 2 hours.  Invalidated on any course mutation.
# ---------------------------------------------------------------------------

@router.get("/calendar", response_model=List[schemas.CourseCalendarItem])
@limiter.limit("120/minute")
async def read_courses_calendar(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Returns a compact list (≤ 1000) of courses with schedules + logistics only,
    intended for the Training Calendar page.  Curriculum blocks are excluded to
    keep the payload small and the response fast.
    """
    cache_key = "courses:calendar:v1"
    cached_data = await redis_manager.get(cache_key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except Exception:
            pass

    courses = await crud.course.get_multi(
        db,
        skip=0,
        limit=1000,
        summary=True,   # excludes curriculum_blocks
        active_only=False,  # no slow Python filter — let browser filter by date
    )

    response.headers["X-Total-Count"] = str(len(courses))

    try:
        await redis_manager.set(
            cache_key,
            json.dumps(jsonable_encoder(courses)),
            expire=7200,  # 2 hours
        )
    except Exception:
        pass

    return courses


@router.get("/categories", response_model=List[dict])
@limiter.limit("60/minute")
async def read_course_categories(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(deps.get_db),
    active_only: bool = True,
) -> Any:
    """
    Retrieve unique categories and their sub-categories.
    """
    cache_key = f"courses:categories:active_only={active_only}"
    cached_data = await redis_manager.get(cache_key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except Exception:
            pass

    courses = await crud.course.get_multi(
        db,
        skip=0,
        limit=100000,
        active_only=active_only,
        summary=True
    )
    
    category_map = {}
    for course in courses:
        cat = course.category
        sub_cat = course.sub_category
        if not cat:
            continue
        if cat not in category_map:
            category_map[cat] = set()
        if sub_cat:
            category_map[cat].add(sub_cat)
            
    result = []
    for cat, sub_cats in sorted(category_map.items()):
        result.append({
            "category": cat,
            "sub_categories": sorted(list(sub_cats))
        })

    try:
        await redis_manager.set(
            cache_key,
            json.dumps(result),
            expire=3600
        )
    except Exception:
        pass

    return result


@router.get("/{slug}", response_model=schemas.Course)
@limiter.limit("60/minute")
async def read_course_by_slug(
    request: Request,
    response: Response,
    slug: str,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Get a specific course by slug.
    """
    cache_key = f"courses:detail:{slug}"
    cached_data = await redis_manager.get(cache_key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except Exception:
            pass

    course = await crud.course.get_by_slug(db, slug=slug)
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found",
        )
    try:
        await redis_manager.set(
            cache_key,
            json.dumps(jsonable_encoder(course)),
            expire=3600
        )
    except Exception:
        pass
    return course

@router.put("/{id}", response_model=schemas.Course)
async def update_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("manage_courses")),
    id: UUID,
    course_in: schemas.CourseUpdate,
) -> Any:
    """
    Update a course.
    """
    course = await crud.course.get(db, id=id)
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found",
        )
    updated_course = await crud.course.update(db, db_obj=course, obj_in=course_in)
    
    # Invalidate cached catalogs, details, and dashboard stats
    await redis_manager.delete_pattern("courses:*")
    await redis_manager.delete_pattern("dashboard:*")
    
    await sse_manager.broadcast("courses_updated", {"action": "update", "id": str(updated_course.id)})
    await sse_manager.broadcast("draft_deleted", {"user_id": str(current_user.id), "reason": "save"})
    return updated_course

@router.delete("/{id}", response_model=schemas.Course)
async def delete_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.check_permission("delete_courses")),
    id: UUID,
) -> Any:
    """
    Delete a course.
    """
    course = await crud.course.get(db, id=id)
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found",
        )
    removed_course = await crud.course.remove(db, id=id)
    
    # Invalidate cached catalogs, details, and dashboard stats
    await redis_manager.delete_pattern("courses:*")
    await redis_manager.delete_pattern("dashboard:*")
    
    await sse_manager.broadcast("courses_updated", {"action": "delete", "id": str(id)})
    return removed_course
