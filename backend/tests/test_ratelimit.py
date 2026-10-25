"""Claim rate limiting: only rejected codes count; fail-closed when Redis is down."""

import fakeredis
import pytest
import redis.exceptions
from fastapi import HTTPException

from app.config import Settings
from app.services.ratelimit import ClaimLimiter, RateLimitUnavailable, ensure_not_blocked, record_rejection


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis()


async def test_blocked_only_after_limit_rejections(redis_client):
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    for _ in range(4):
        await limiter.hit("device", "u1")
    assert not await limiter.blocked("device", "u1", 5)
    await limiter.hit("device", "u1")
    assert await limiter.blocked("device", "u1", 5)


async def test_scopes_and_keys_are_independent(redis_client):
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    for _ in range(5):
        await limiter.hit("device", "u1")
    assert not await limiter.blocked("device", "u2", 5)
    assert not await limiter.blocked("tenant", "u1", 5)


async def test_window_is_set_on_first_hit(redis_client):
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    await limiter.hit("device", "u1")
    ttl = await redis_client.ttl("rate:claim:device:u1")
    assert 0 < ttl <= 3600
    await limiter.hit("device", "u1")
    assert await redis_client.ttl("rate:claim:device:u1") <= ttl  # later hits do not extend it


class _BrokenRedis:
    def pipeline(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("down")

    async def get(self, *args, **kwargs):
        raise redis.exceptions.TimeoutError("slow")


async def test_redis_error_raises_unavailable():
    limiter = ClaimLimiter(_BrokenRedis(), window_seconds=3600)
    with pytest.raises(RateLimitUnavailable):
        await limiter.hit("device", "u1")
    with pytest.raises(RateLimitUnavailable):
        await limiter.blocked("device", "u1", 5)


async def test_successful_attempts_do_not_count(redis_client):
    settings = Settings(_env_file=None)
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    for i in range(20):  # twenty clean activations in a row for one tenant
        await ensure_not_blocked(limiter, device_uuid=f"d{i}", tenant_id="acme", settings=settings)


async def test_tenant_blocked_after_five_rejections(redis_client):
    settings = Settings(_env_file=None)
    limiter = ClaimLimiter(redis_client, window_seconds=3600)
    for i in range(5):  # five wrong codes on five different devices
        await record_rejection(limiter, device_uuid=f"d{i}", tenant_id="acme")
    with pytest.raises(HTTPException) as exc:
        await ensure_not_blocked(limiter, device_uuid="d9", tenant_id="acme", settings=settings)
    assert exc.value.status_code == 429
    await ensure_not_blocked(limiter, device_uuid="d9", tenant_id="tenant-b", settings=settings)
