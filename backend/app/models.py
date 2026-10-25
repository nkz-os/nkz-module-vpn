"""Domain records of the device registry (immutable)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

DeviceType = Literal["rover", "gateway", "sensor"]
DeviceState = Literal["PENDING", "CLAIMED", "REVOKED"]

DEVICE_TYPES: tuple[str, ...] = ("rover", "gateway", "sensor")


@dataclass(frozen=True)
class Device:
    device_uuid: str
    tenant_id: str
    device_type: str
    display_name: str | None
    claim_version: int
    state: str
    claimed_at: datetime | None
    claimed_by: str | None
    revoked_at: datetime | None
    revoked_by: str | None
    headscale_user: str | None
    preauth_key_id: str | None
    preauth_expires: datetime | None
    node_id: str | None
    node_hostname: str | None
    node_ip: str | None
    ngsi_entity_id: str | None
    ngsi_entity_type: str | None
    cert_fingerprint: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DeviceEvent:
    id: int
    device_uuid: str
    tenant_id: str
    action: str
    actor_sub: str
    ip: str | None
    details: dict[str, Any] | None
    created_at: datetime
