"""
Entity Manager Client

Creates NGSI-LD entities in entity-manager when devices are claimed (ZTP flow).
Called best-effort from the /devices/claim endpoint: a failure here does NOT
abort the claim — the device is still activated in Headscale.

Operators can create the entity manually via the platform UI if this call fails.
"""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def create_ngsi_entity(
    *,
    token: str,
    entity_id: str,
    entity_type: str,
    device_uuid: str,
    device_name: Optional[str],
    device_type: str,
    tenant_id: str,
) -> None:
    """
    POST /api/entities to entity-manager with a minimal NGSI-LD representation.

    Raises httpx.HTTPError on failure — callers should catch and log.
    """
    url = f"{settings.ENTITY_MANAGER_URL}/api/entities"

    # Ensure FIWARE Smart Data Models compliance
    # Map generic device types to valid NGSI-LD types
    normalized_type = entity_type
    if device_type.lower() in ["robot", "ros", "zenoh", "tractor", "agv"]:
        normalized_type = "AgriculturalMachine"
    elif device_type.lower() in ["sensor", "gateway"]:
        normalized_type = "Device"

    payload = {
        "id": entity_id,
        "type": normalized_type,
        # Standard NGSI-LD attributes
        "name": {
            "type": "Property",
            "value": device_name or device_uuid,
        },
        "status": {
            "type": "Property",
            "value": "offline",
        },
        # Device-specific metadata
        "deviceUUID": {
            "type": "Property",
            "value": device_uuid,
        },
        "deviceType": {
            "type": "Property",
            "value": device_type,
        },
        "networkLayer": {
            "type": "Property",
            "value": "headscale",
        },
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Fiware-Service": tenant_id,
        "Link": (
            f'<{settings.CONTEXT_URL}>; '
            f'rel="http://www.w3.org/ns/json-ld#context"; '
            f'type="application/ld+json"'
        ),
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code == 409:
            # Entity already exists — update is acceptable
            logger.info("Entity %s already exists in entity-manager, skipping.", entity_id)
            return
        r.raise_for_status()
        logger.info("Entity %s (%s) created in entity-manager.", entity_id, entity_type)
