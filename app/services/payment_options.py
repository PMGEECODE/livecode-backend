from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.payment_option import PaymentOptionSetting


DEFAULT_PAYMENT_OPTIONS = {
    "mpesa": {
        "label": "M-Pesa STK Push",
        "disabled_message": "M-Pesa payments are temporarily unavailable. Please choose another payment option or contact support.",
    },
    "paystack": {
        "label": "Paystack Cards",
        "disabled_message": "Card payments are temporarily unavailable. Please choose another payment option or contact support.",
    },
    "paypal": {
        "label": "PayPal",
        "disabled_message": "PayPal payments are temporarily unavailable. Please choose another payment option or contact support.",
    },
    "stripe": {
        "label": "Stripe Cards",
        "disabled_message": "Stripe card payments are temporarily unavailable. Please choose another payment option or contact support.",
    },
    "offline": {
        "label": "Offline / Bank Transfer",
        "disabled_message": "Offline payment registration is temporarily unavailable. Please contact support for assistance.",
    },
}

PAYMENT_METHOD_PROVIDER_MAP = {
    "online": "mpesa",
    "mpesa": "mpesa",
    "paystack": "paystack",
    "paypal": "paypal",
    "stripe": "stripe",
    "offline": "offline",
    "bank transfer": "offline",
    "bank transfer / offline": "offline",
}


def normalize_payment_provider(provider: str | None) -> str:
    key = str(provider or "").strip().lower()
    return PAYMENT_METHOD_PROVIDER_MAP.get(key, key)


async def ensure_default_payment_options(db: AsyncSession) -> None:
    result = await db.execute(select(PaymentOptionSetting))
    existing = {item.provider: item for item in result.scalars().all()}
    changed = False

    for provider, config in DEFAULT_PAYMENT_OPTIONS.items():
        setting = existing.get(provider)
        if not setting:
            db.add(
                PaymentOptionSetting(
                    provider=provider,
                    label=config["label"],
                    is_enabled=True,
                    disabled_message=config["disabled_message"],
                )
            )
            changed = True
        else:
            if setting.label != config["label"]:
                setting.label = config["label"]
                changed = True
            if not setting.disabled_message:
                setting.disabled_message = config["disabled_message"]
                changed = True

    if changed:
        await db.commit()


async def list_payment_options(db: AsyncSession) -> list[PaymentOptionSetting]:
    await ensure_default_payment_options(db)
    result = await db.execute(select(PaymentOptionSetting))
    settings = {item.provider: item for item in result.scalars().all()}
    return [settings[provider] for provider in DEFAULT_PAYMENT_OPTIONS if provider in settings]


async def get_payment_option(db: AsyncSession, provider: str) -> PaymentOptionSetting:
    normalized = normalize_payment_provider(provider)
    await ensure_default_payment_options(db)
    result = await db.execute(
        select(PaymentOptionSetting).filter(PaymentOptionSetting.provider == normalized)
    )
    setting = result.scalars().first()
    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment option not found.")
    return setting


async def ensure_payment_provider_enabled(db: AsyncSession, provider: str) -> None:
    setting = await get_payment_option(db, provider)
    if setting.is_enabled:
        return

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=setting.disabled_message
        or f"{setting.label} is temporarily unavailable. Please choose another payment option or contact support.",
    )
