import logging
from slowapi import Limiter
from fastapi import Request
from app.core.config import settings
import sys

logger = logging.getLogger(__name__)

is_test = "pytest" in sys.modules

def get_client_ip(request: Request) -> str:
    # Check X-Forwarded-For header (e.g. set by Nginx)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    # Check X-Real-IP header
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
        
    # Fallback to direct client host
    return request.client.host if request.client else "127.0.0.1"

try:
    if is_test:
        logger.info("🛡️ Disabling Rate Limiter for test suite running...")
        limiter = Limiter(
            key_func=get_client_ip,
            enabled=False,
        )
    else:
        logger.info("🛡️ Initializing production-grade distributed Rate Limiter with Redis storage backend...")
        limiter = Limiter(
            key_func=get_client_ip,
            storage_uri=settings.REDIS_URL,
            headers_enabled=True,
        )
except Exception as e:
    logger.error("⚠️ Redis not available for Rate Limiter storage. Falling back to local in-memory storage: %s", repr(e))
    limiter = Limiter(
        key_func=get_client_ip,
        headers_enabled=True,
        enabled=not is_test,
    )

