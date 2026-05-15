from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app import crud, schemas
from app.api import deps

router = APIRouter()

@router.get("/", response_model=List[schemas.Service])
async def read_services(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve services.
    """
    services = await crud.service.get_multi(db, skip=skip, limit=limit)
    return services

@router.post("/", response_model=schemas.Service)
async def create_service(
    *,
    db: AsyncSession = Depends(deps.get_db),
    service_in: schemas.ServiceCreate,
) -> Any:
    """
    Create new service.
    """
    service = await crud.service.get_by_slug(db, slug=service_in.slug)
    if service:
        raise HTTPException(
            status_code=400,
            detail="The service with this slug already exists in the system.",
        )
    return await crud.service.create(db, obj_in=service_in)

@router.get("/{slug}", response_model=schemas.Service)
async def read_service_by_slug(
    slug: str,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Get a specific service by slug.
    """
    service = await crud.service.get_by_slug(db, slug=slug)
    if not service:
        raise HTTPException(
            status_code=404,
            detail="Service not found",
        )
    return service
