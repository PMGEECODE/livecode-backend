from app.api.v1.endpoints.registration_modules import router
from app.api.v1.endpoints.registration_modules.emails import process_registration_email

__all__ = ["router", "process_registration_email"]
