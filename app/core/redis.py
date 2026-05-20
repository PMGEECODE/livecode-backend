import logging
import json
from typing import Any, Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self) -> None:
        self.client: Optional[aioredis.Redis] = None

    async def init(self) -> None:
        """Initialize the async Redis connection pool."""
        try:
            logger.info("🔌 Initializing Async Redis client connection pool...")
            self.client = aioredis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=2.0,
                socket_keepalive=True,
                retry_on_timeout=True
            )
            # Test connection
            await self.client.ping()
            logger.info("✅ Redis connection established successfully.")
        except Exception as e:
            logger.error("❌ Failed to initialize Redis connection pool: %s", repr(e))
            self.client = None

    async def close(self) -> None:
        """Safely close the Redis connection pool."""
        if self.client:
            logger.info("🔌 Closing Redis client connection pool...")
            await self.client.aclose()
            logger.info("✅ Redis client connection pool closed.")

    async def get(self, key: str) -> Optional[str]:
        """Get key from Redis safely with graceful fallback."""
        if not self.client:
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.warning("⚠️ Redis GET error for key %s: %s", key, repr(e))
            return None

    async def set(self, key: str, value: str, expire: int = 3600) -> bool:
        """Set key-value pair in Redis safely with an expiration in seconds."""
        if not self.client:
            return False
        try:
            await self.client.set(key, value, ex=expire)
            return True
        except Exception as e:
            logger.warning("⚠️ Redis SET error for key %s: %s", key, repr(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis safely."""
        if not self.client:
            return False
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.warning("⚠️ Redis DELETE error for key %s: %s", key, repr(e))
            return False

    async def delete_pattern(self, pattern: str) -> bool:
        """Delete all keys matching a specific pattern safely using SCAN (non-blocking)."""
        if not self.client:
            return False
        try:
            deleted = 0
            cursor: int = 0
            while True:
                cursor, keys = await self.client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await self.client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            if deleted:
                logger.info("🧹 Evicted %d cached keys matching pattern: %s", deleted, pattern)
            return True
        except Exception as e:
            logger.warning("⚠️ Redis DELETE pattern error for pattern %s: %s", pattern, repr(e))
            return False

redis_manager = RedisManager()
