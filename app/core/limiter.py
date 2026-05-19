import logging
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    logger.info("🛡️ Initializing production-grade distributed Rate Limiter with Redis storage backend...")
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=settings.REDIS_URL,
        headers_enabled=True,
    )
except Exception as e:
    logger.error("⚠️ Redis not available for Rate Limiter storage. Falling back to local in-memory storage: %s", repr(e))
    limiter = Limiter(
        key_func=get_remote_address,
        headers_enabled=True,
    )
