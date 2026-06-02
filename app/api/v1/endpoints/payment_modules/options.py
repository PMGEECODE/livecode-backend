from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.api import deps
from app.api.deps import get_db
from app.db.models.payment_option import PaymentOptionSetting
from app.schemas.payment import PaymentOptionResponse, PaymentOptionsResponse, PaymentOptionUpdate
from app.services.payment_options import get_payment_option, list_payment_options

router = APIRouter()


@router.get(
    "/availability",
    response_model=PaymentOptionsResponse,
    summary="List public payment option availability",
)
async def payment_availability(
    db: AsyncSession = Depends(get_db),
) -> PaymentOptionsResponse:
    options = await list_payment_options(db)
    return PaymentOptionsResponse(options=options)


@router.get(
    "/admin/options",
    response_model=PaymentOptionsResponse,
    summary="List payment options for administrators",
)
async def admin_payment_options(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> PaymentOptionsResponse:
    options = await list_payment_options(db)
    return PaymentOptionsResponse(options=options)


@router.patch(
    "/admin/options/{provider}",
    response_model=PaymentOptionResponse,
    summary="Enable or disable a payment option",
)
async def update_payment_option(
    provider: str,
    payload: PaymentOptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    setting: PaymentOptionSetting = await get_payment_option(db, provider)
    setting.is_enabled = payload.is_enabled
    if payload.disabled_message is not None:
        setting.disabled_message = payload.disabled_message.strip() or None

    db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting
