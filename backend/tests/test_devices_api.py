"""Device lifecycle routes: validate, claim, list, status, events, revoke."""

import json
import logging

import httpx
import pytest
import respx

from app.db.repo import DeviceRepo
from app.services.claim_code import generate_claim_code
from tests.conftest import FACTORY_SECRET, HEADSCALE_URL, ORION_URL, gateway_headers

UUID = "3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c"
UUID_2 = "8a7b6c5d-4e3f-4a2b-9c1d-0e1f2a3b4c5d"
CODE = generate_claim_code(UUID, FACTORY_SECRET, 1)
TWIN_ID = f"urn:ngsi-ld:ManufacturingMachine:acme:{UUID}"
ACME = gateway_headers("acme", "TenantAdmin")
OTHER = gateway_headers("tenant-b", "TenantAdmin")
PLATFORM = gateway_headers("platform-ops", "PlatformAdmin")
UPSERT = f"{ORION_URL}/ngsi-ld/v1/entityOperations/upsert"


async def register(db, device_uuid=UUID, tenant="acme", device_type="rover"):
    async with db.platform_tx() as conn:
        await DeviceRepo(conn).create_pending(device_uuid, tenant, device_type, "Mini 01", 1)


async def state_of(db, device_uuid=UUID):
    async with db.platform_tx() as conn:
        return await DeviceRepo(conn).get(device_uuid)


async def actions_of(db, device_uuid=UUID):
    async with db.platform_tx() as conn:
        return [e.action for e in await DeviceRepo(conn).list_events(device_uuid)]


@pytest.fixture
def mocks():
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{HEADSCALE_URL}/api/v1/user").mock(return_value=httpx.Response(200, json={"users": []}))
        router.post(f"{HEADSCALE_URL}/api/v1/user").mock(
            return_value=httpx.Response(200, json={"user": {"id": "1", "name": "acme"}}))
        router.post(f"{HEADSCALE_URL}/api/v1/preauthkey", name="preauth").mock(return_value=httpx.Response(200, json={
            "preAuthKey": {"id": "13", "key": "tskey-secret-value", "expiration": "2030-01-01T00:00:00Z",
                           "aclTags": ["tag:field-device"]}}))
        router.post(f"{HEADSCALE_URL}/api/v1/preauthkey/expire", name="expire").mock(
            return_value=httpx.Response(200, json={}))
        router.get(f"{HEADSCALE_URL}/api/v1/node", name="nodes").mock(
            return_value=httpx.Response(200, json={"nodes": []}))
        router.post(UPSERT, name="upsert").mock(return_value=httpx.Response(204))
        router.patch(f"{ORION_URL}/ngsi-ld/v1/entities/{TWIN_ID}/attrs", name="patch").mock(
            return_value=httpx.Response(204))
        router.delete(f"{ORION_URL}/ngsi-ld/v1/entities/{TWIN_ID}", name="twin_delete").mock(
            return_value=httpx.Response(204))
        router.get(f"{HEADSCALE_URL}/api/v1/preauthkey", name="keys").mock(
            return_value=httpx.Response(200, json={"preAuthKeys": []}))
        yield router


def node_list(node_id="21", key_id="13", hostname=UUID, online=True):
    return {"nodes": [{"id": node_id, "name": hostname, "givenName": hostname, "ipAddresses": ["192.0.2.21"],
                       "online": online, "lastSeen": "2026-10-25T08:00:00Z", "preAuthKey": {"id": key_id},
                       "forcedTags": ["tag:field-device"]}]}


async def claim(api, headers=ACME, code=CODE, device_uuid=UUID, **extra):
    return await api.post("/api/vpn/devices/claim",
                          json={"device_uuid": device_uuid, "claim_code": code, **extra}, headers=headers)


# --- validate ---------------------------------------------------------------

async def test_validate_ok(api, db, mocks):
    await register(db)
    r = await api.post("/api/vpn/devices/validate", json={"device_uuid": UUID, "claim_code": CODE}, headers=ACME)
    assert r.status_code == 200
    assert r.json() == {"valid": True, "device_uuid": UUID, "device_type": "rover",
                        "display_name": "Mini 01", "state": "PENDING"}
    assert (await state_of(db)).state == "PENDING"


async def test_validate_other_tenant_404(api, db, mocks):
    await register(db)
    r = await api.post("/api/vpn/devices/validate", json={"device_uuid": UUID, "claim_code": CODE}, headers=OTHER)
    assert r.status_code == 404


async def test_validate_wrong_code_400_and_event(api, db, mocks):
    await register(db)
    r = await api.post("/api/vpn/devices/validate", json={"device_uuid": UUID, "claim_code": "V1-AAAAAAAA"},
                       headers=ACME)
    assert r.status_code == 400
    assert await actions_of(db) == ["CLAIM_REJECTED"]


async def test_tenant_role_required(api, db, mocks):
    await register(db)
    r = await api.post("/api/vpn/devices/validate", json={"device_uuid": UUID, "claim_code": CODE},
                       headers=gateway_headers("acme", "Farmer"))
    assert r.status_code == 403


# --- claim ------------------------------------------------------------------

async def test_claim_happy_path(api, db, mocks):
    await register(db)
    r = await claim(api, display_name="Showroom mini")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "CLAIMED"
    assert data["device_type"] == "rover"
    assert data["display_name"] == "Showroom mini"
    assert data["ngsi_entity_id"] == TWIN_ID
    assert data["network"]["login_server"] == "https://vpn.example.test"
    assert data["network"]["preauth_key"] == "tskey-secret-value"
    assert data["network"]["hostname"] == UUID
    assert data["network"]["expires_at"].startswith("2030-01-01")
    preauth = json.loads(mocks["preauth"].calls.last.request.content)
    assert preauth["aclTags"] == ["tag:field-device"] and preauth["user"] == "acme"
    twin = json.loads(mocks["upsert"].calls.last.request.content)[0]
    assert twin["type"] == "ManufacturingMachine" and twin["category"]["value"] == "robot"
    assert twin["name"]["value"] == "Showroom mini"
    device = await state_of(db)
    assert (device.state, device.preauth_key_id, device.headscale_user) == ("CLAIMED", "13", "acme")
    assert (device.ngsi_entity_id, device.ngsi_entity_type) == (TWIN_ID, "ManufacturingMachine")
    assert device.display_name == "Showroom mini"
    assert await actions_of(db) == ["CLAIMED"]


async def test_claim_twice_409(api, db, mocks):
    await register(db)
    assert (await claim(api)).status_code == 200
    assert (await claim(api)).status_code == 409


async def test_claim_revoked_410(api, db, mocks):
    await register(db)
    async with db.platform_tx() as conn:
        await DeviceRepo(conn).mark_revoked(UUID, revoked_by="u0")
    assert (await claim(api)).status_code == 410


async def test_claim_unknown_device_404(api, db, mocks):
    assert (await claim(api)).status_code == 404


async def test_claim_rate_limited_429(api, db, mocks):
    await register(db)
    statuses = [(await claim(api, code="V1-AAAAAAAA")).status_code for _ in range(6)]
    assert statuses == [400] * 5 + [429]


async def test_claim_orion_down_creates_no_key(api, db, mocks):
    await register(db)
    mocks["upsert"].mock(return_value=httpx.Response(500))
    r = await claim(api)
    assert r.status_code == 502
    assert not mocks["preauth"].called
    assert (await state_of(db)).state == "PENDING"


async def test_claim_headscale_down_leaves_pending(api, db, mocks):
    await register(db)
    mocks["preauth"].mock(return_value=httpx.Response(500))
    r = await claim(api)
    assert r.status_code == 502
    assert (await state_of(db)).state == "PENDING"
    assert mocks["twin_delete"].called  # no twin left saying CLAIMED
    assert (await claim(api)).status_code == 502  # still claimable once Headscale is back


async def test_claim_db_failure_expires_key(api, db, mocks, monkeypatch):
    await register(db)

    async def broken(self, *args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(DeviceRepo, "mark_claimed", broken)
    r = await claim(api)
    assert r.status_code == 502
    expire = json.loads(mocks["expire"].calls.last.request.content)
    assert expire == {"user": "acme", "key": "tskey-secret-value"}
    assert (await state_of(db)).state == "PENDING"


async def test_claim_redis_down_503(api, db, mocks, services):
    from app.services.ratelimit import RateLimitUnavailable

    async def down(*args, **kwargs):
        raise RateLimitUnavailable("down")

    services.limiter.blocked = down
    await register(db)
    assert (await claim(api)).status_code == 503


async def test_no_secret_in_logs(api, db, mocks, caplog):
    caplog.set_level(logging.DEBUG)
    await register(db)
    await claim(api)
    await claim(api, code="V1-AAAAAAAA")
    assert "tskey-secret-value" not in caplog.text
    assert CODE not in caplog.text


# --- list / status / events ------------------------------------------------------

async def test_list_is_tenant_scoped(api, db, mocks):
    await register(db, UUID, "acme")
    await register(db, UUID_2, "tenant-b")
    r = await api.get("/api/vpn/devices", headers=ACME)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert [d["device_uuid"] for d in data["devices"]] == [UUID]
    assert data["devices"][0]["node"] is None


async def test_list_all_tenants_requires_platform_admin(api, db, mocks):
    await register(db, UUID, "acme")
    await register(db, UUID_2, "tenant-b")
    assert (await api.get("/api/vpn/devices?all_tenants=true", headers=ACME)).status_code == 403
    r = await api.get("/api/vpn/devices?all_tenants=true", headers=PLATFORM)
    assert {d["tenant_id"] for d in r.json()["devices"]} == {"acme", "tenant-b"}


async def test_get_reconciles_node(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["nodes"].mock(return_value=httpx.Response(200, json=node_list()))
    r = await api.get(f"/api/vpn/devices/{UUID}", headers=ACME)
    assert r.status_code == 200
    assert r.json()["node"] == {"online": True, "last_seen": "2026-10-25T08:00:00Z", "ip": "192.0.2.21"}
    device = await state_of(db)
    assert (device.node_id, device.node_ip) == ("21", "192.0.2.21")
    assert await actions_of(db) == ["CLAIMED", "NODE_SEEN"]


async def test_list_survives_headscale_outage(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["nodes"].mock(return_value=httpx.Response(500))
    r = await api.get("/api/vpn/devices", headers=ACME)
    assert r.status_code == 200
    assert r.json()["devices"][0]["node"] is None


async def test_get_other_tenant_404(api, db, mocks):
    await register(db)
    assert (await api.get(f"/api/vpn/devices/{UUID}", headers=OTHER)).status_code == 404


async def test_events_lists_actions_in_order(api, db, mocks):
    await register(db)
    await claim(api, code="V1-AAAAAAAA")
    await claim(api)
    r = await api.get(f"/api/vpn/devices/{UUID}/events", headers=ACME)
    assert r.status_code == 200
    assert [e["action"] for e in r.json()["events"]] == ["CLAIM_REJECTED", "CLAIMED"]


# --- revoke ------------------------------------------------------------------------

async def test_revoke_with_node_deletes_node_and_patches_twin(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["nodes"].mock(return_value=httpx.Response(200, json=node_list()))
    delete = mocks.delete(f"{HEADSCALE_URL}/api/v1/node/21").mock(return_value=httpx.Response(200, json={}))
    r = await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)
    assert r.status_code == 204
    assert delete.called
    assert json.loads(mocks["patch"].calls.last.request.content) == {
        "deviceState": {"type": "Property", "value": "REVOKED"}}
    assert (await state_of(db)).state == "REVOKED"
    assert (await claim(api)).status_code == 410


async def test_revoke_without_node(api, db, mocks):
    await register(db)
    await claim(api)
    delete = mocks.delete(url__regex=rf"{HEADSCALE_URL}/api/v1/node/.*")
    r = await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)
    assert r.status_code == 204
    assert not delete.called
    assert mocks["patch"].called
    assert (await state_of(db)).state == "REVOKED"
    assert await actions_of(db) == ["CLAIMED", "REVOKED"]


async def test_revoke_pending_device_touches_nothing_remote(api, db, mocks):
    await register(db)
    r = await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)
    assert r.status_code == 204
    assert not mocks["patch"].called
    assert not mocks["nodes"].called
    assert (await state_of(db)).state == "REVOKED"


async def test_revoke_node_delete_failure_keeps_state(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["nodes"].mock(return_value=httpx.Response(200, json=node_list()))
    mocks.delete(f"{HEADSCALE_URL}/api/v1/node/21").mock(return_value=httpx.Response(500))
    r = await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)
    assert r.status_code == 502
    assert (await state_of(db)).state == "CLAIMED"


async def test_revoke_survives_orion_outage(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["patch"].mock(return_value=httpx.Response(500))
    r = await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)
    assert r.status_code == 204
    assert (await state_of(db)).state == "REVOKED"


async def test_revoke_twice_409(api, db, mocks):
    await register(db)
    assert (await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)).status_code == 204
    assert (await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)).status_code == 409


async def test_onboarding_many_devices_is_not_throttled(api, db, mocks):
    uuids = [f"00000000-0000-4000-8000-00000000000{i}" for i in range(6)]
    for u in uuids:
        await register(db, device_uuid=u)
        code = generate_claim_code(u, FACTORY_SECRET, 1)
        v = await api.post("/api/vpn/devices/validate", json={"device_uuid": u, "claim_code": code}, headers=ACME)
        assert v.status_code == 200
        assert (await claim(api, device_uuid=u, code=code)).status_code == 200


async def test_sensor_claim_creates_no_vpn_key(api, db, mocks):
    await register(db, device_type="sensor")
    sensor_twin = f"urn:ngsi-ld:Device:acme:{UUID}"
    r = await claim(api)
    assert r.status_code == 200
    assert r.json()["network"] is None
    assert r.json()["ngsi_entity_id"] == sensor_twin
    assert not mocks["preauth"].called
    assert (await state_of(db)).preauth_key_id is None


async def test_revoke_headscale_unreachable_keeps_state(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["nodes"].mock(return_value=httpx.Response(500))
    r = await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)
    assert r.status_code == 502
    assert (await state_of(db)).state == "CLAIMED"


async def test_revoke_ignores_stale_node_id(api, db, mocks):
    await register(db)
    await claim(api)
    async with db.platform_tx() as conn:
        await DeviceRepo(conn).set_node(UUID, node_id="77", node_hostname=UUID, node_ip="192.0.2.77")
    delete = mocks.delete(url__regex=rf"{HEADSCALE_URL}/api/v1/node/.*")
    r = await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)  # node removed outside the module
    assert r.status_code == 204
    assert not delete.called
    assert (await state_of(db)).state == "REVOKED"


async def test_revoke_expires_unused_key(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["keys"].mock(return_value=httpx.Response(200, json={"preAuthKeys": [
        {"id": "13", "key": "tskey-secret-value", "used": False, "expiration": "2030-01-01T00:00:00Z"}]}))
    r = await api.delete(f"/api/vpn/devices/{UUID}", headers=ACME)
    assert r.status_code == 204
    assert json.loads(mocks["expire"].calls.last.request.content) == {"user": "acme", "key": "tskey-secret-value"}
    assert (await state_of(db)).state == "REVOKED"


# --- reissue key -------------------------------------------------------------------

async def test_reissue_key_for_device_that_never_joined(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["keys"].mock(return_value=httpx.Response(200, json={"preAuthKeys": [
        {"id": "13", "key": "tskey-secret-value", "used": False, "expiration": "2030-01-01T00:00:00Z"}]}))
    mocks["preauth"].mock(return_value=httpx.Response(200, json={"preAuthKey": {
        "id": "14", "key": "tskey-new-value", "expiration": "2030-01-02T00:00:00Z", "aclTags": ["tag:field-device"]}}))
    r = await api.post(f"/api/vpn/devices/{UUID}/reissue-key", headers=ACME)
    assert r.status_code == 200
    data = r.json()
    assert data["preauth_key"] == "tskey-new-value" and data["hostname"] == UUID
    assert json.loads(mocks["expire"].calls.last.request.content) == {"user": "acme", "key": "tskey-secret-value"}
    assert (await state_of(db)).preauth_key_id == "14"
    assert (await actions_of(db))[-1] == "KEY_REISSUED"


async def test_reissue_refused_when_node_joined(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["nodes"].mock(return_value=httpx.Response(200, json=node_list()))
    r = await api.post(f"/api/vpn/devices/{UUID}/reissue-key", headers=ACME)
    assert r.status_code == 409
    assert mocks["preauth"].call_count == 1  # only the original claim


async def test_reissue_refused_for_pending_and_sensor(api, db, mocks):
    await register(db)
    assert (await api.post(f"/api/vpn/devices/{UUID}/reissue-key", headers=ACME)).status_code == 409
    await register(db, device_uuid=UUID_2, device_type="sensor")
    await claim(api, device_uuid=UUID_2, code=generate_claim_code(UUID_2, FACTORY_SECRET, 1))
    assert (await api.post(f"/api/vpn/devices/{UUID_2}/reissue-key", headers=ACME)).status_code == 409


async def test_reissue_headscale_down_changes_nothing(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["nodes"].mock(return_value=httpx.Response(500))
    r = await api.post(f"/api/vpn/devices/{UUID}/reissue-key", headers=ACME)
    assert r.status_code == 502
    assert (await state_of(db)).preauth_key_id == "13"


async def test_reissue_other_tenant_404(api, db, mocks):
    await register(db)
    await claim(api)
    assert (await api.post(f"/api/vpn/devices/{UUID}/reissue-key", headers=OTHER)).status_code == 404


async def test_network_unknown_when_headscale_down(api, db, mocks):
    await register(db)
    await claim(api)
    mocks["nodes"].mock(return_value=httpx.Response(500))
    listed = (await api.get("/api/vpn/devices", headers=ACME)).json()["devices"][0]
    single = (await api.get(f"/api/vpn/devices/{UUID}", headers=ACME)).json()
    assert listed["node"] is None and listed["network_unknown"] is True
    assert single["network_unknown"] is True


async def test_network_known_when_not_joined(api, db, mocks):
    await register(db)
    await claim(api)
    listed = (await api.get("/api/vpn/devices", headers=ACME)).json()["devices"][0]
    assert listed["node"] is None and listed["network_unknown"] is False
