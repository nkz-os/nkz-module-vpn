"""SDM twin of a claimed device: only @context terms, no secrets, via the SDK OrionClient."""

import json

import httpx
import pytest
import respx
from nkz_platform_sdk import OrionClient

from app.services.twin import TwinError, TwinWriter, build_twin, twin_id

ORION = "http://orion.test:1026"
UUID = "3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c"


def test_twin_id_rover_is_manufacturing_machine():
    assert twin_id("rover", "acme", UUID) == ("ManufacturingMachine", f"urn:ngsi-ld:ManufacturingMachine:acme:{UUID}")


def test_twin_id_gateway_and_sensor_are_devices():
    assert twin_id("gateway", "acme", UUID) == ("Device", f"urn:ngsi-ld:Device:acme:{UUID}")
    assert twin_id("sensor", "acme", UUID) == ("Device", f"urn:ngsi-ld:Device:acme:{UUID}")


def test_build_rover_twin():
    assert build_twin("rover", "acme", UUID, "Mini 01") == {
        "id": f"urn:ngsi-ld:ManufacturingMachine:acme:{UUID}",
        "type": "ManufacturingMachine",
        "name": {"type": "Property", "value": "Mini 01"},
        "serialNumber": {"type": "Property", "value": UUID},
        "deviceState": {"type": "Property", "value": "CLAIMED"},
        "category": {"type": "Property", "value": "robot"},
    }


def test_build_sensor_twin_is_device_without_category():
    twin = build_twin("sensor", "acme", UUID, "Probe")
    assert twin["type"] == "Device"
    assert "category" not in twin
    assert "location" not in twin


def test_name_falls_back_to_uuid():
    assert build_twin("gateway", "acme", UUID, None)["name"]["value"] == UUID


def test_unknown_type_rejected():
    with pytest.raises(ValueError):
        twin_id("drone", "acme", UUID)


@pytest.fixture
async def writer():
    w = TwinWriter("acme", orion=OrionClient("acme", base_url=ORION, context_url="http://ctx.test/context.json"))
    try:
        yield w
    finally:
        await w.close()


@respx.mock
async def test_upsert_calls_batch_upsert(writer):
    route = respx.post(f"{ORION}/ngsi-ld/v1/entityOperations/upsert").mock(return_value=httpx.Response(204))
    twin = build_twin("rover", "acme", UUID, "Mini 01")
    assert await writer.upsert(twin) == twin["id"]
    req = route.calls.last.request
    assert req.headers["Content-Type"] == "application/ld+json"
    assert req.headers["NGSILD-Tenant"] == "acme"
    body = json.loads(req.content)
    assert body[0]["@context"] == ["http://ctx.test/context.json"]
    assert body[0]["id"] == twin["id"]


@respx.mock
async def test_upsert_failure_raises_twin_error(writer):
    respx.post(f"{ORION}/ngsi-ld/v1/entityOperations/upsert").mock(return_value=httpx.Response(500))
    with pytest.raises(TwinError):
        await writer.upsert(build_twin("rover", "acme", UUID, None))


@respx.mock
async def test_upsert_partial_error_raises_twin_error(writer):
    respx.post(f"{ORION}/ngsi-ld/v1/entityOperations/upsert").mock(return_value=httpx.Response(
        207, json={"success": [], "errors": [{"entityId": "x", "error": {"status": 400}}]}))
    with pytest.raises(TwinError):
        await writer.upsert(build_twin("rover", "acme", UUID, None))


@respx.mock
async def test_upsert_connection_error_raises_twin_error(writer):
    respx.post(f"{ORION}/ngsi-ld/v1/entityOperations/upsert").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(TwinError):
        await writer.upsert(build_twin("rover", "acme", UUID, None))


@respx.mock
async def test_mark_revoked_patches_attrs(writer):
    entity = f"urn:ngsi-ld:ManufacturingMachine:acme:{UUID}"
    route = respx.patch(f"{ORION}/ngsi-ld/v1/entities/{entity}/attrs").mock(return_value=httpx.Response(204))
    await writer.mark_revoked(entity)
    req = route.calls.last.request
    assert req.headers["Content-Type"] == "application/json"
    assert "rel=\"http://www.w3.org/ns/json-ld#context\"" in req.headers["Link"]
    assert json.loads(req.content) == {"deviceState": {"type": "Property", "value": "REVOKED"}}


@respx.mock
async def test_delete_removes_entity(writer):
    entity = f"urn:ngsi-ld:ManufacturingMachine:acme:{UUID}"
    route = respx.delete(f"{ORION}/ngsi-ld/v1/entities/{entity}").mock(return_value=httpx.Response(204))
    await writer.delete(entity)
    assert route.called


@respx.mock
async def test_delete_missing_entity_is_fine(writer):
    entity = f"urn:ngsi-ld:ManufacturingMachine:acme:{UUID}"
    respx.delete(f"{ORION}/ngsi-ld/v1/entities/{entity}").mock(return_value=httpx.Response(404))
    await writer.delete(entity)
