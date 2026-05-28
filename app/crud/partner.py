from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.db.models.partner import TrustedPartner
from app.schemas.partner import TrustedPartnerCreate, TrustedPartnerUpdate


class CRUDTrustedPartner(CRUDBase[TrustedPartner, TrustedPartnerCreate, TrustedPartnerUpdate]):

    async def get_all_active(self, db: AsyncSession) -> List[TrustedPartner]:
        """Return all active partners ordered by display_order then name."""
        result = await db.execute(
            select(TrustedPartner)
            .where(TrustedPartner.is_active == True)  # noqa: E712
            .order_by(TrustedPartner.display_order.asc(), TrustedPartner.name.asc())
        )
        return list(result.scalars().all())

    async def get_all(self, db: AsyncSession) -> List[TrustedPartner]:
        """Return all partners (active + inactive) for admin management."""
        result = await db.execute(
            select(TrustedPartner).order_by(
                TrustedPartner.display_order.asc(), TrustedPartner.name.asc()
            )
        )
        return list(result.scalars().all())


trusted_partner = CRUDTrustedPartner(TrustedPartner)
