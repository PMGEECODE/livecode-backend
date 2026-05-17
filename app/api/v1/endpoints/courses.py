from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app import crud, schemas
from app.api import deps
from app.core.sse import sse_manager

router = APIRouter()

@router.get("/", response_model=List[schemas.Course])
async def read_courses(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve courses.
    """
    courses = await crud.course.get_multi(db, skip=skip, limit=limit)
    return courses

@router.post("/", response_model=schemas.Course)
async def create_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
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
    await sse_manager.broadcast("courses_updated", {"action": "create", "id": str(new_course.id)})
    return new_course

@router.get("/{slug}", response_model=schemas.Course)
async def read_course_by_slug(
    slug: str,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Get a specific course by slug.
    """
    course = await crud.course.get_by_slug(db, slug=slug)
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found",
        )
    return course

@router.put("/{id}", response_model=schemas.Course)
async def update_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
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
    await sse_manager.broadcast("courses_updated", {"action": "update", "id": str(updated_course.id)})
    return updated_course

@router.delete("/{id}", response_model=schemas.Course)
async def delete_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
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
    await sse_manager.broadcast("courses_updated", {"action": "delete", "id": str(id)})
    return removed_course
