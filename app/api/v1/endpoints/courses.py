from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app import crud, schemas
from app.api import deps

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
    return await crud.course.create(db, obj_in=course_in)

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
    id: int,
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
    return await crud.course.update(db, db_obj=course, obj_in=course_in)

@router.delete("/{id}", response_model=schemas.Course)
async def delete_course(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: int,
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
    return await crud.course.remove(db, id=id)
