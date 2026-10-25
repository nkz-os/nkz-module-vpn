"""Schema, forced RLS and repository against a real PostgreSQL."""

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repo import DeviceExists, DeviceRepo, InvalidTransition

UUID_A = "3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c"
UUID_B = "8a7b6c5d-4e3f-4a2b-9c1d-0e1f2a3b4c5d"


async def _register(db, device_uuid=UUID_A, tenant="acme"):
    async with db.platform_tx() as conn:
        return await DeviceRepo(conn).create_pending(device_uuid, tenant, "rover", "Mini 01", 1)


async def test_migrations_are_idempotent(pg_dsn):
    assert await run_migrations(pg_dsn) == []


async def test_no_guc_sees_nothing(db, pg_dsn):
    await _register(db)
    conn = await asyncpg.connect(pg_dsn)  # the owner role, without the tenant setting
    try:
        assert await conn.fetchval("SELECT count(*) FROM devices") == 0
    finally:
        await conn.close()


async def test_tenant_isolation(db):
    await _register(db, UUID_A, "acme")
    async with db.tenant_tx("tenant-b") as conn:
        assert await DeviceRepo(conn).list_devices() == []
        assert await DeviceRepo(conn).get(UUID_A) is None
    async with db.tenant_tx("acme") as conn:
        devices = await DeviceRepo(conn).list_devices()
    assert [d.device_uuid for d in devices] == [UUID_A]


async def test_tenant_cannot_insert_for_another_tenant(db):
    async with db.tenant_tx("acme") as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await DeviceRepo(conn).create_pending(UUID_B, "tenant-b", "rover", None, 1)


async def test_platform_scope_sees_all(db):
    await _register(db, UUID_A, "acme")
    await _register(db, UUID_B, "tenant-b")
    async with db.platform_tx() as conn:
        devices = await DeviceRepo(conn).list_devices()
    assert {d.tenant_id for d in devices} == {"acme", "tenant-b"}


async def test_create_pending_returns_device(db):
    device = await _register(db)
    assert (device.device_uuid, device.tenant_id, device.device_type, device.state) == (
        UUID_A, "acme", "rover", "PENDING")
    assert device.display_name == "Mini 01"
    assert device.claim_version == 1


async def test_create_pending_duplicate_raises(db):
    await _register(db)
    with pytest.raises(DeviceExists):
        await _register(db)


async def test_state_transitions(db):
    await _register(db)
    async with db.tenant_tx("acme") as conn:
        repo = DeviceRepo(conn)
        locked = await repo.get_for_update(UUID_A)
        assert locked.state == "PENDING"
        claimed = await repo.mark_claimed(
            UUID_A, claimed_by="u1", headscale_user="acme", preauth_key_id="42",
            preauth_expires=None, ngsi_entity_id="urn:ngsi-ld:ManufacturingMachine:acme:" + UUID_A,
            ngsi_entity_type="ManufacturingMachine", display_name=None,
        )
        assert claimed.state == "CLAIMED"
        assert claimed.preauth_key_id == "42"
        assert claimed.display_name == "Mini 01"  # None keeps the factory name
        assert claimed.claimed_at is not None
        with_node = await repo.set_node(UUID_A, node_id="7", node_hostname=UUID_A, node_ip="192.0.2.9")
        assert (with_node.node_id, with_node.node_ip) == ("7", "192.0.2.9")
        revoked = await repo.mark_revoked(UUID_A, revoked_by="u2")
        assert revoked.state == "REVOKED"
        assert revoked.revoked_by == "u2"


async def test_claim_requires_pending(db):
    await _register(db)
    async with db.tenant_tx("acme") as conn:
        repo = DeviceRepo(conn)
        await repo.mark_revoked(UUID_A, revoked_by="u1")
        with pytest.raises(InvalidTransition):
            await repo.mark_claimed(
                UUID_A, claimed_by="u1", headscale_user="acme", preauth_key_id="1",
                preauth_expires=None, ngsi_entity_id="x", ngsi_entity_type="ManufacturingMachine",
                display_name=None,
            )
        with pytest.raises(InvalidTransition):
            await repo.mark_revoked(UUID_A, revoked_by="u1")


async def test_list_events_ordered(db):
    await _register(db)
    async with db.tenant_tx("acme") as conn:
        repo = DeviceRepo(conn)
        await repo.add_event(UUID_A, "acme", "REGISTERED", "u0", None, None)
        await repo.add_event(UUID_A, "acme", "CLAIM_REJECTED", "u1", "203.0.113.7", {"reason": "bad_code"})
        await repo.add_event(UUID_A, "acme", "CLAIMED", "u1", "203.0.113.7", None)
        events = await repo.list_events(UUID_A)
    assert [e.action for e in events] == ["REGISTERED", "CLAIM_REJECTED", "CLAIMED"]
    assert events[1].details == {"reason": "bad_code"}
    assert events[1].ip == "203.0.113.7"


async def test_events_are_tenant_scoped(db):
    await _register(db)
    async with db.tenant_tx("acme") as conn:
        await DeviceRepo(conn).add_event(UUID_A, "acme", "CLAIMED", "u1", None, None)
    async with db.tenant_tx("tenant-b") as conn:
        assert await DeviceRepo(conn).list_events(UUID_A) == []
