"""
SDM twin of a claimed device in Orion-LD.

A rover is a ManufacturingMachine with category "robot" (platform IoT model:
Device for sensors and gateways, ManufacturingMachine for machinery). The twin
carries only terms defined in the platform @context — name, serialNumber,
deviceState, category — and nothing from provisioning: no claim data, no
Headscale ids, no invented location. Module-specific attributes (robotics
operation mode, parcel link) are added later by the modules that own them.
"""

from typing import Any

import httpx
from nkz_platform_sdk import OrionClient

_TWIN_TYPES = {"rover": "ManufacturingMachine", "gateway": "Device", "sensor": "Device"}


class TwinError(Exception):
    pass


def twin_id(device_type: str, tenant_id: str, device_uuid: str) -> tuple[str, str]:
    try:
        entity_type = _TWIN_TYPES[device_type]
    except KeyError:
        raise ValueError(f"unknown device type: {device_type}") from None
    return entity_type, f"urn:ngsi-ld:{entity_type}:{tenant_id}:{device_uuid}"


def _prop(value: Any) -> dict[str, Any]:
    return {"type": "Property", "value": value}


def build_twin(device_type: str, tenant_id: str, device_uuid: str, display_name: str | None) -> dict[str, Any]:
    entity_type, entity_id = twin_id(device_type, tenant_id, device_uuid)
    twin = {
        "id": entity_id,
        "type": entity_type,
        "name": _prop(display_name or device_uuid),
        "serialNumber": _prop(device_uuid),
        "deviceState": _prop("CLAIMED"),
    }
    if device_type == "rover":
        twin["category"] = _prop("robot")
    return twin


class TwinWriter:
    def __init__(self, tenant_id: str, orion: OrionClient | None = None):
        self._orion = orion or OrionClient(tenant_id)

    async def close(self) -> None:
        await self._orion.close()

    async def upsert(self, twin: dict[str, Any]) -> str:
        try:
            result = await self._orion.upsert_entities_batch([twin])
        except httpx.HTTPError as exc:
            raise TwinError(f"orion upsert failed: {type(exc).__name__}") from None
        if result.get("errors"):
            raise TwinError(f"orion upsert rejected {twin['id']}")
        return twin["id"]

    async def mark_revoked(self, entity_id: str) -> None:
        try:
            await self._orion.update_entity_attrs(entity_id, {"deviceState": _prop("REVOKED")})
        except httpx.HTTPError as exc:
            raise TwinError(f"orion patch failed: {type(exc).__name__}") from None
