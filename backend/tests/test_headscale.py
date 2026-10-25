"""Headscale 0.23 REST client (grpc-gateway JSON: lowerCamelCase, uint64 ids as strings)."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.services.headscale import HeadscaleClient, HeadscaleError, headscale_user_for

BASE = "http://headscale.test:8080"


@pytest.fixture
async def client():
    c = HeadscaleClient(BASE, "api-key")
    try:
        yield c
    finally:
        await c.close()


def test_headscale_user_for_tenant():
    assert headscale_user_for("Acme_Corp") == "acme-corp"
    assert headscale_user_for("acme") == "acme"


@respx.mock
async def test_ensure_user_creates_when_absent(client):
    respx.get(f"{BASE}/api/v1/user").mock(return_value=httpx.Response(200, json={"users": [{"id": "1", "name": "other"}]}))
    create = respx.post(f"{BASE}/api/v1/user").mock(return_value=httpx.Response(200, json={"user": {"id": "2", "name": "acme"}}))
    await client.ensure_user("acme")
    assert create.called
    assert json.loads(create.calls.last.request.content) == {"name": "acme"}
    assert create.calls.last.request.headers["Authorization"] == "Bearer api-key"


@respx.mock
async def test_ensure_user_noop_when_present(client):
    respx.get(f"{BASE}/api/v1/user").mock(return_value=httpx.Response(200, json={"users": [{"id": "2", "name": "acme"}]}))
    create = respx.post(f"{BASE}/api/v1/user")
    await client.ensure_user("acme")
    assert not create.called


@respx.mock
async def test_create_preauth_key_sends_acl_tags_and_expiration(client):
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    route = respx.post(f"{BASE}/api/v1/preauthkey").mock(return_value=httpx.Response(200, json={
        "preAuthKey": {"user": "acme", "id": "13", "key": "secret-key", "reusable": False, "ephemeral": False,
                       "used": False, "expiration": expiry, "aclTags": ["tag:field-device"]}}))
    key = await client.create_preauth_key("acme", ttl_minutes=30)
    body = json.loads(route.calls.last.request.content)
    assert body["user"] == "acme"
    assert body["aclTags"] == ["tag:field-device"]
    assert body["reusable"] is False and body["ephemeral"] is False
    requested = datetime.strptime(body["expiration"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert abs((requested - datetime.now(timezone.utc)) - timedelta(minutes=30)) < timedelta(seconds=60)
    assert (key.id, key.key) == ("13", "secret-key")
    assert key.expires_at.tzinfo is not None


@respx.mock
async def test_expire_preauth_key(client):
    route = respx.post(f"{BASE}/api/v1/preauthkey/expire").mock(return_value=httpx.Response(200, json={}))
    await client.expire_preauth_key("acme", "secret-key")
    assert json.loads(route.calls.last.request.content) == {"user": "acme", "key": "secret-key"}


NODES = {"nodes": [
    {"id": "7", "name": "laptop", "givenName": "laptop", "user": {"name": "acme"},
     "ipAddresses": ["192.0.2.7"], "online": False, "lastSeen": "2026-10-24T10:00:00Z",
     "preAuthKey": {"id": "3"}, "forcedTags": []},
    {"id": "9", "name": "dev-host", "givenName": "3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c", "user": {"name": "acme"},
     "ipAddresses": ["192.0.2.9", "fd7a:115c:a1e0::9"], "online": True, "lastSeen": "2026-10-25T00:00:00Z",
     "preAuthKey": {"id": "13"}, "forcedTags": ["tag:field-device"]},
]}


@respx.mock
async def test_find_node_by_preauth_id_then_hostname(client):
    respx.get(f"{BASE}/api/v1/node", params={"user": "acme"}).mock(return_value=httpx.Response(200, json=NODES))
    by_key = await client.find_node("acme", preauth_key_id="13", hostname="nope")
    assert (by_key.id, by_key.ip, by_key.online, by_key.forced_tags) == ("9", "192.0.2.9", True, ("tag:field-device",))
    by_name = await client.find_node("acme", preauth_key_id="999", hostname="3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c")
    assert by_name.id == "9"
    assert by_name.last_seen == datetime(2026, 10, 25, tzinfo=timezone.utc)


@respx.mock
async def test_find_node_returns_none(client):
    respx.get(f"{BASE}/api/v1/node", params={"user": "acme"}).mock(return_value=httpx.Response(200, json={"nodes": []}))
    assert await client.find_node("acme", preauth_key_id="13", hostname="x") is None


@respx.mock
async def test_5xx_raises_headscale_error(client):
    respx.post(f"{BASE}/api/v1/preauthkey").mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(HeadscaleError) as exc:
        await client.create_preauth_key("acme", ttl_minutes=30)
    assert exc.value.status == 500


@respx.mock
async def test_timeout_raises_headscale_error(client):
    respx.get(f"{BASE}/api/v1/user").mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(HeadscaleError) as exc:
        await client.ensure_user("acme")
    assert exc.value.status is None


@respx.mock
async def test_delete_node(client):
    route = respx.delete(f"{BASE}/api/v1/node/9").mock(return_value=httpx.Response(200, json={}))
    await client.delete_node("9")
    assert route.called


@respx.mock
async def test_errors_never_carry_the_key(client):
    respx.post(f"{BASE}/api/v1/preauthkey/expire").mock(return_value=httpx.Response(500, text="no"))
    with pytest.raises(HeadscaleError) as exc:
        await client.expire_preauth_key("acme", "secret-key")
    assert "secret-key" not in str(exc.value)
