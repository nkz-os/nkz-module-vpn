"""
Redis-backed rate limiter with per-tenant and per-IP windows.

Used by the /devices/claim endpoint to prevent brute-force attacks
on Claim Codes. Two windows: tenant-level and IP-level.
"""

import logging
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis_url: str = settings.REDIS_URL):
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            kwargs = {"encoding": "utf-8", "decode_responses": True}
            if settings.REDIS_PASSWORD:
                kwargs["password"] = settings.REDIS_PASSWORD
            self._redis = aioredis.from_url(self._redis_url, **kwargs)
        return self._redis

    async def check(
        self, key: str, max_attempts: int, window_seconds: int
    ) -> bool:
        """
        Returns True if the request is allowed, False if rate-limited.

        Uses Redis INCR + EXPIRE for atomic counting within the window.
        """
        r = await self._get_redis()
        try:
            current = await r.get(key)
            if current is not None and int(current) >= max_attempts:
                ttl = await r.ttl(key)
                logger.warning(
                    "Rate limit hit for key prefix %s (ttl=%ss)",
                    key.rsplit(":", 1)[0], ttl,
                )
                return False
            pipe = r.pipeline()
            pipe.incr(key)
            if current is None:
                pipe.expire(key, window_seconds)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error("Redis rate limit check failed: %s — allowing request", e)
            return True  # Fail open — don't block legitimate traffic


    def exempt(self, func):
        return func

limiter = RateLimiter()
