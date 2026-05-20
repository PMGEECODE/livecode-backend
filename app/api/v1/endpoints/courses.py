import json
from typing import Any, List
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

@router.get("/", response_model=List[schemas.Course])
@limiter.limit("60/minute")
async def read_courses(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve courses.
    """
    cache_key = f"courses:list:skip={skip}:limit={limit}"
    cached_data = await redis_manager.get(cache_key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except Exception:
            pass

    courses = await crud.course.get_multi(db, skip=skip, limit=limit)
    try:
        await redis_manager.set(
            cache_key,
            json.dumps(jsonable_encoder(courses)),
            expire=3600
        )
    except Exception:
        pass
    return courses

@router.post("/", response_model=schemas.Course)
async def create_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    return new_course

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
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    return updated_course

@router.delete("/{id}", response_model=schemas.Course)
async def delete_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
