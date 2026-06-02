from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Livecode Analytics Service"
    ANALYTICS_DATABASE_URL: str = "postgresql://postgres:.7447_GEE@localhost/analytics"
    ANALYTICS_QUEUE_MAX_SIZE: int = 10_000
    ANALYTICS_FLUSH_BATCH_SIZE: int = 250
    ANALYTICS_FLUSH_INTERVAL_SECONDS: float = 2.0
    ANALYTICS_BATCH_MAX_EVENTS: int = 50
    ANALYTICS_RETENTION_DAYS: int = 365
    ANALYTICS_ADMIN_SUBJECTS: str = ""

    SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    BACKEND_CORS_ORIGINS: str = ""

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip().rstrip("/") for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def admin_subjects(self) -> set[str]:
        return {subject.strip() for subject in self.ANALYTICS_ADMIN_SUBJECTS.split(",") if subject.strip()}

    model_config = {
        "case_sensitive": True,
        "env_file": ".env",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
