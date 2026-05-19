import json
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    PROJECT_NAME: str = "Livecode Technologies API"

    # Database
    DATABASE_URL: str

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return self.DATABASE_URL

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Email Settings
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = "info@livecodetechnologies.com"
    EMAILS_FROM_NAME: str = "Livecode Technologies"
    COMPANY_NOTIFICATION_EMAIL: str = ""

    # Security & CORS
    # Stored as a raw str to prevent pydantic-settings from attempting
    # json.loads() on the comma-separated value before validators run.
    # Access the parsed list via the `cors_origins` property.
    BACKEND_CORS_ORIGINS: str = "*"
    JWT_ALGORITHM: str = "HS256"

    @property
    def cors_origins(self) -> List[str]:
        """Return BACKEND_CORS_ORIGINS as a parsed list of strings."""
        raw = self.BACKEND_CORS_ORIGINS.strip()
        if raw.startswith("["):
            try:
                return [str(o).strip() for o in json.loads(raw) if str(o).strip()]
            except json.JSONDecodeError:
                pass
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    model_config = {
        "case_sensitive": True,
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()
