"""Internal device lookup for in-cluster callers (robotics): X-Internal-Service-Secret only."""

import httpx
import respx

from app.db.repo import DeviceRepo
from tests.conftest import HEADSCALE_URL

UUID = "3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c"
PATH = f"/api/vpn/internal/devices/{UUID}"
SECRET = {"X-Internal-Service-Secret": "internal-secret"}


async def _claimed(db, tenant="tenant-b"):
    async with db.platform_tx() as conn:
        repo = DeviceRepo(conn)
        await repo.create_pending(UUID, tenant, "rover", "Mini", 1)
        await repo.mark_claimed(
            UUID, claimed_by="u1", headscale_user=tenant, preauth_key_id="13", preauth_expires=None,
            ngsi_entity_id=f"urn:ngsi-ld:ManufacturingMachine:{tenant}:{UUID}",
            ngsi_entity_type="ManufacturingMachine", display_name=None,
        )


async def test_internal_requires_secret(api, db):
    await _claimed(db)
    assert (await api.get(PATH)).status_code == 401


async def test_internal_wrong_secret_401(api, db):
    await _claimed(db)
    assert (await api.get(PATH, headers={"X-Internal-Service-Secret": "nope"})).status_code == 401


async def test_internal_gateway_headers_are_not_enough(api, db):
    await _claimed(db)
    r = await api.get(PATH, headers={"X-Tenant-ID": "tenant-b", "X-User-ID": "u1", "X-User-Roles": "PlatformAdmin"})
    assert r.status_code == 401


async def test_internal_404(api, db):
    assert (await api.get(PATH, headers=SECRET)).status_code == 404


async def test_internal_returns_device_any_tenant(api, db):
    await _claimed(db, tenant="tenant-b")
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{HEADSCALE_URL}/api/v1/node").mock(return_value=httpx.Response(200, json={"nodes": []}))
        r = await api.get(PATH, headers=SECRET)
    assert r.status_code == 200
    assert r.json() == {
        "device_uuid": UUID, "tenant_id": "tenant-b", "device_type": "rover", "state": "CLAIMED",
        "ngsi_entity_id": f"urn:ngsi-ld:ManufacturingMachine:tenant-b:{UUID}",
        "ngsi_entity_type": "ManufacturingMachine", "node": None,
    }
