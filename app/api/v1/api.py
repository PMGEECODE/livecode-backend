from fastapi import APIRouter
from app.api.v1.endpoints import auth, blog, courses, users, services, realtime, registration, contacts, dashboard, payments, upload, media, partners, trainers, analytics, newsletter, products, support

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"], prefix="/auth")
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(blog.router, prefix="/blog", tags=["blog"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(realtime.router, prefix="/realtime", tags=["realtime"])
api_router.include_router(registration.router, prefix="/registrations", tags=["registrations"])
api_router.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(payments.router, prefix="/endpoints/payments", tags=["payments"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(partners.router, prefix="/partners", tags=["partners"])
api_router.include_router(trainers.router, prefix="/trainers", tags=["trainers"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(newsletter.router, prefix="/newsletter", tags=["newsletter"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(support.router, prefix="/support", tags=["support"])

