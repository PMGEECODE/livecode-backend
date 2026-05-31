from fastapi import APIRouter

from app.api.v1.endpoints.registration_modules import admin, documents, public

router = APIRouter()
router.include_router(public.router)
router.include_router(admin.router)
router.include_router(documents.router)
