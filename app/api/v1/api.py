from fastapi import APIRouter
from app.api.v1.endpoints import auth, blog, courses, users, services, realtime, registration, contacts, dashboard

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

