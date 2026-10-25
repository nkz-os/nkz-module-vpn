"""Factory routes: PlatformAdmin only, platform scope, claim code never stored."""

import re

import nkz_platform_sdk.auth as sdk_auth
from nkz_platform_sdk.crypto import generate_hmac_signature

from app.db.repo import DeviceRepo
from app.services.claim_code import generate_claim_code
from tests.conftest import FACTORY_SECRET, gateway_headers, make_csr

UUID = "3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c"
ADMIN = gateway_headers(tenant="platform-ops", roles="PlatformAdmin")
REGISTER = "/api/vpn/factory/register-device"
SIGN = "/api/vpn/factory/sign-csr"


def body(**overrides):
    data = {"device_uuid": UUID, "device_type": "rover", "tenant_id": "acme", "display_name": "Mini 01"}
    data.update(overrides)
    return data


async def test_register_requires_platform_admin(api):
    r = await api.post(REGISTER, json=body(), headers=gateway_headers(roles="TenantAdmin"))
    assert r.status_code == 403


async def test_register_requires_gateway_headers(api):
    r = await api.post(REGISTER, json=body())
    assert r.status_code == 401


async def test_register_returns_claim_code_and_persists(api, db):
    r = await api.post(REGISTER, json=body(), headers=ADMIN)
    assert r.status_code == 201
    data = r.json()
    assert re.fullmatch(r"V1-[A-Z2-7]{8}", data["claim_code"])
    assert data["claim_code"] == generate_claim_code(UUID, FACTORY_SECRET, 1)
    assert (data["device_uuid"], data["device_type"], data["tenant_id"]) == (UUID, "rover", "acme")
    async with db.platform_tx() as conn:
        repo = DeviceRepo(conn)
        device = await repo.get(UUID)
        events = await repo.list_events(UUID)
    assert (device.state, device.tenant_id, device.claim_version) == ("PENDING", "acme", 1)
    assert device.display_name == "Mini 01"
    assert [e.action for e in events] == ["REGISTERED"]
    assert events[0].actor_sub == "u1"


async def test_register_duplicate_409(api):
    assert (await api.post(REGISTER, json=body(), headers=ADMIN)).status_code == 201
    assert (await api.post(REGISTER, json=body(), headers=ADMIN)).status_code == 409


async def test_register_bad_type_422(api):
    assert (await api.post(REGISTER, json=body(device_type="drone"), headers=ADMIN)).status_code == 422


async def test_register_bad_uuid_422(api):
    assert (await api.post(REGISTER, json=body(device_uuid="not-a-uuid"), headers=ADMIN)).status_code == 422


async def test_register_bad_tenant_422(api):
    assert (await api.post(REGISTER, json=body(tenant_id="Acme_Corp"), headers=ADMIN)).status_code == 422


async def test_sign_csr_unregistered_404(api):
    csr, _ = make_csr(UUID, "rover")
    r = await api.post(SIGN, json={"csr_pem": csr, "device_uuid": UUID}, headers=ADMIN)
    assert r.status_code == 404


async def test_sign_csr_cn_mismatch_400(api, services):
    await api.post(REGISTER, json=body(), headers=ADMIN)
    csr, _ = make_csr("someone-else", "rover")
    r = await api.post(SIGN, json={"csr_pem": csr, "device_uuid": UUID}, headers=ADMIN)
    assert r.status_code == 400
    assert services.pki.calls == []


async def test_sign_csr_ou_mismatch_400(api, services):
    await api.post(REGISTER, json=body(), headers=ADMIN)
    csr, _ = make_csr(UUID, "sensor")
    r = await api.post(SIGN, json={"csr_pem": csr, "device_uuid": UUID}, headers=ADMIN)
    assert r.status_code == 400


async def test_sign_csr_garbage_400(api):
    await api.post(REGISTER, json=body(), headers=ADMIN)
    r = await api.post(SIGN, json={"csr_pem": "-----BEGIN NOPE-----", "device_uuid": UUID}, headers=ADMIN)
    assert r.status_code == 400


async def test_sign_csr_ok_stores_fingerprint(api, services, db):
    await api.post(REGISTER, json=body(), headers=ADMIN)
    csr, _ = make_csr(UUID, "rover")
    r = await api.post(SIGN, json={"csr_pem": csr, "device_uuid": UUID}, headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")
    assert data["ca_pem"] == services.pki.ca_pem
    assert services.pki.calls == [(UUID, "rover")]
    async with db.platform_tx() as conn:
        repo = DeviceRepo(conn)
        device = await repo.get(UUID)
        events = await repo.list_events(UUID)
    assert re.fullmatch(r"[0-9a-f]{64}", device.cert_fingerprint)
    assert [e.action for e in events] == ["REGISTERED", "CERT_SIGNED"]


async def test_hmac_required_rejects_unsigned(api, monkeypatch):
    monkeypatch.setattr(sdk_auth, "REQUIRE_HMAC", True)
    monkeypatch.setattr(sdk_auth, "HMAC_SECRET", "hmac-secret")
    r = await api.post(REGISTER, json=body(), headers=ADMIN)
    assert r.status_code == 401


async def test_hmac_required_accepts_signed(api, monkeypatch):
    monkeypatch.setattr(sdk_auth, "REQUIRE_HMAC", True)
    monkeypatch.setattr(sdk_auth, "HMAC_SECRET", "hmac-secret")
    signature = generate_hmac_signature("hmac-secret", "", "platform-ops")
    r = await api.post(REGISTER, json=body(), headers={**ADMIN, "X-Auth-Signature": signature})
    assert r.status_code == 201
