from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.db.models.service import Service
from app.schemas.service import ServiceCreate, ServiceUpdate

class CRUDService(CRUDBase[Service, ServiceCreate, ServiceUpdate]):
    async def get_by_slug(self, db: AsyncSession, *, slug: str) -> Optional[Service]:
        result = await db.execute(select(Service).filter(Service.slug == slug))
        return result.scalars().first()

service = CRUDService(Service)
