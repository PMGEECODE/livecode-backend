from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app import crud, schemas
from app.api import deps
from app.core.limiter import limiter
import uuid

router = APIRouter()

@router.post("/", response_model=schemas.Contact)
@limiter.limit("5/minute")
async def create_contact(
    request: Request,
    response: Response,
    *,
    db: AsyncSession = Depends(deps.get_db),
    contact_in: schemas.ContactCreate,
) -> Any:
    """
    Create new contact message.
    """
    return await crud.contact.create(db, obj_in=contact_in)

@router.get("/", response_model=List[schemas.Contact])
async def read_contacts(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve contacts.
    """
    contacts = await crud.contact.get_multi(db, skip=skip, limit=limit)
    return contacts

@router.patch("/{id}", response_model=schemas.Contact)
async def update_contact(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: uuid.UUID,
    contact_in: schemas.ContactUpdate,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a contact message.
    """
    contact = await crud.contact.get(db, id=id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact = await crud.contact.update(db, db_obj=contact, obj_in=contact_in)
    return contact

@router.delete("/{id}", response_model=schemas.Contact)
async def delete_contact(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: uuid.UUID,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a contact message.
    """
    contact = await crud.contact.get(db, id=id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact = await crud.contact.remove(db, id=id)
    return contact
