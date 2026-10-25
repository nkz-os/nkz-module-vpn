"""
Claim rate limiting (Redis, fixed window).

Only REJECTED claim codes count: brute force means wrong codes, and an
organisation activating many devices in a row must not be throttled. Limits are
per device and per organisation. There is no per-IP bucket: behind the
api-gateway every request arrives from the gateway's own address, so an IP
bucket would be one shared bucket for the whole platform.

The limiter fails CLOSED: if Redis cannot be reached the claim is refused
(503), never served without a limit.
"""

import redis.asyncio as redis_async
import redis.exceptions
from fastapi import HTTPException, status


class RateLimitUnavailable(Exception):
    pass


class ClaimLimiter:
    def __init__(self, client: redis_async.Redis, window_seconds: int):
        self._redis = client
        self._window = window_seconds

    @staticmethod
    def _key(scope: str, key: str) -> str:
        return f"rate:claim:{scope}:{key}"

    async def blocked(self, scope: str, key: str, limit: int) -> bool:
        try:
            count = await self._redis.get(self._key(scope, key))
        except redis.exceptions.RedisError as exc:
            raise RateLimitUnavailable(type(exc).__name__) from None
        return count is not None and int(count) >= limit

    async def hit(self, scope: str, key: str) -> None:
        name = self._key(scope, key)
        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.set(name, 0, ex=self._window, nx=True)  # window starts at the first rejection
            pipe.incr(name)
            await pipe.execute()
        except redis.exceptions.RedisError as exc:
            raise RateLimitUnavailable(type(exc).__name__) from None


async def ensure_not_blocked(limiter: ClaimLimiter, *, device_uuid: str, tenant_id: str, settings) -> None:
    if await limiter.blocked("device", device_uuid, settings.claim_limit_per_device) or await limiter.blocked(
        "tenant", tenant_id, settings.claim_limit_per_tenant
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many claim attempts")


async def record_rejection(limiter: ClaimLimiter, *, device_uuid: str, tenant_id: str) -> None:
    await limiter.hit("device", device_uuid)
    await limiter.hit("tenant", tenant_id)
