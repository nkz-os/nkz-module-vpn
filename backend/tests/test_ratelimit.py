"""Claim rate limiting: fixed window per scope, fail-closed when Redis is down."""

import fakeredis
import pytest
import redis.exceptions
from fastapi import HTTPException

from app.config import Settings
from app.services.ratelimit import ClaimLimiter, RateLimitUnavailable, check_all


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis()


async def test_allows_until_limit_then_blocks(redis_client):
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    results = [await limiter.check("device", "u1", 5) for _ in range(6)]
    assert results == [True] * 5 + [False]


async def test_scopes_and_keys_are_independent(redis_client):
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    for _ in range(5):
        await limiter.check("device", "u1", 5)
    assert await limiter.check("device", "u2", 5)
    assert await limiter.check("tenant", "u1", 5)


async def test_window_is_set_on_first_hit(redis_client):
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    await limiter.check("device", "u1", 5)
    ttl = await redis_client.ttl("rate:claim:device:u1")
    assert 0 < ttl <= 3600
    await limiter.check("device", "u1", 5)
    assert await redis_client.ttl("rate:claim:device:u1") <= ttl  # later hits do not extend it


class _BrokenRedis:
    def pipeline(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("down")


async def test_redis_error_raises_unavailable():
    limiter = ClaimLimiter(_BrokenRedis(), window_seconds=3600)
    with pytest.raises(RateLimitUnavailable):
        await limiter.check("device", "u1", 5)


async def test_check_all_429_on_tenant_limit(redis_client):
    settings = Settings(_env_file=None)
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    for i in range(5):  # five different devices of the same tenant
        await check_all(limiter, device_uuid=f"d{i}", tenant_id="acme", ip="203.0.113.7", settings=settings)
    with pytest.raises(HTTPException) as exc:
        await check_all(limiter, device_uuid="d9", tenant_id="acme", ip="203.0.113.7", settings=settings)
    assert exc.value.status_code == 429


async def test_check_all_without_ip_skips_ip_scope(redis_client):
    settings = Settings(_env_file=None)
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    await check_all(limiter, device_uuid="d1", tenant_id="acme", ip=None, settings=settings)
    assert await redis_client.exists("rate:claim:ip:None") == 0
