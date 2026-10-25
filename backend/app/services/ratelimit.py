"""
Claim rate limiting (Redis, fixed window).

The claim endpoint is the only place a claim code can be brute-forced, so the
limiter fails CLOSED: if Redis cannot be reached the claim is refused (503),
never served without a limit.
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

    async def check(self, scope: str, key: str, limit: int) -> bool:
        """Count one attempt; True while the window holds at most `limit` attempts."""
        name = f"rate:claim:{scope}:{key}"
        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.set(name, 0, ex=self._window, nx=True)  # window starts at the first hit
            pipe.incr(name)
            _, count = await pipe.execute()
        except redis.exceptions.RedisError as exc:
            raise RateLimitUnavailable(type(exc).__name__) from None
        return int(count) <= limit


async def check_all(limiter: ClaimLimiter, *, device_uuid: str, tenant_id: str, ip: str | None, settings) -> None:
    checks = [("device", device_uuid, settings.claim_limit_per_device),
              ("tenant", tenant_id, settings.claim_limit_per_tenant)]
    if ip:
        checks.append(("ip", ip, settings.claim_limit_per_ip))
    for scope, key, limit in checks:
        if not await limiter.check(scope, key, limit):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many claim attempts")
