from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.db.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactUpdate

class CRUDContact(CRUDBase[Contact, ContactCreate, ContactUpdate]):
    pass

contact = CRUDContact(Contact)
