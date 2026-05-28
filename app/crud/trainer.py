from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.db.models.trainer import TrainerApplication
from app.schemas.trainer import TrainerApplicationCreate, TrainerApplicationUpdate


class CRUDTrainerApplication(CRUDBase[TrainerApplication, TrainerApplicationCreate, TrainerApplicationUpdate]):
    
    async def get_multi_by_status(
        self, db: AsyncSession, *, status: Optional[str] = None, skip: int = 0, limit: int = 100
    ) -> List[TrainerApplication]:
        """Retrieve applications, optionally filtered by status, ordered by created_at descending."""
        query = select(TrainerApplication)
        if status:
            query = query.where(TrainerApplication.status == status)
        query = query.order_by(TrainerApplication.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())


trainer_application = CRUDTrainerApplication(TrainerApplication)
