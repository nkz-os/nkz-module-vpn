"""
Device registry repository. Operates on a connection already scoped by
Database.tenant_tx / platform_tx; which rows are visible is decided by RLS.

State machine (devices.state):  PENDING -> CLAIMED -> REVOKED,  PENDING -> REVOKED.
"""

from datetime import datetime
from typing import Any

import asyncpg

from app.models import Device, DeviceEvent

_DEVICE_COLUMNS = (
    "device_uuid, tenant_id, device_type, display_name, claim_version, state, claimed_at, claimed_by, "
    "revoked_at, revoked_by, headscale_user, preauth_key_id, preauth_expires, node_id, node_hostname, "
    "node_ip, ngsi_entity_id, ngsi_entity_type, cert_fingerprint, created_at, updated_at"
)


class DeviceExists(Exception):
    pass


class InvalidTransition(Exception):
    pass


def _device(row: asyncpg.Record) -> Device:
    data = dict(row)
    data["device_uuid"] = str(data["device_uuid"])
    if data["node_ip"] is not None:
        data["node_ip"] = str(data["node_ip"]).split("/")[0]
    return Device(**data)


def _event(row: asyncpg.Record) -> DeviceEvent:
    data = dict(row)
    data["device_uuid"] = str(data["device_uuid"])
    if data["ip"] is not None:
        data["ip"] = str(data["ip"]).split("/")[0]
    return DeviceEvent(**data)


class DeviceRepo:
    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    async def create_pending(
        self, device_uuid: str, tenant_id: str, device_type: str, display_name: str | None, claim_version: int
    ) -> Device:
        try:
            row = await self._conn.fetchrow(
                f"INSERT INTO devices (device_uuid, tenant_id, device_type, display_name, claim_version, state) "
                f"VALUES ($1, $2, $3, $4, $5, 'PENDING') RETURNING {_DEVICE_COLUMNS}",
                device_uuid, tenant_id, device_type, display_name, claim_version,
            )
        except asyncpg.UniqueViolationError as exc:
            raise DeviceExists(device_uuid) from exc
        return _device(row)

    async def get(self, device_uuid: str) -> Device | None:
        row = await self._conn.fetchrow(f"SELECT {_DEVICE_COLUMNS} FROM devices WHERE device_uuid = $1", device_uuid)
        return _device(row) if row else None

    async def get_for_update(self, device_uuid: str) -> Device | None:
        row = await self._conn.fetchrow(
            f"SELECT {_DEVICE_COLUMNS} FROM devices WHERE device_uuid = $1 FOR UPDATE", device_uuid
        )
        return _device(row) if row else None

    async def list_devices(self) -> list[Device]:
        rows = await self._conn.fetch(f"SELECT {_DEVICE_COLUMNS} FROM devices ORDER BY created_at, device_uuid")
        return [_device(r) for r in rows]

    async def mark_claimed(
        self,
        device_uuid: str,
        *,
        claimed_by: str,
        headscale_user: str,
        preauth_key_id: str,
        preauth_expires: datetime | None,
        ngsi_entity_id: str,
        ngsi_entity_type: str,
        display_name: str | None,
    ) -> Device:
        row = await self._conn.fetchrow(
            f"UPDATE devices SET state = 'CLAIMED', claimed_at = now(), claimed_by = $2, headscale_user = $3, "
            f"preauth_key_id = $4, preauth_expires = $5, ngsi_entity_id = $6, ngsi_entity_type = $7, "
            f"display_name = COALESCE($8, display_name), updated_at = now() "
            f"WHERE device_uuid = $1 AND state = 'PENDING' RETURNING {_DEVICE_COLUMNS}",
            device_uuid, claimed_by, headscale_user, preauth_key_id, preauth_expires,
            ngsi_entity_id, ngsi_entity_type, display_name,
        )
        if row is None:
            raise InvalidTransition(f"{device_uuid}: claim requires PENDING")
        return _device(row)

    async def mark_revoked(self, device_uuid: str, *, revoked_by: str) -> Device:
        row = await self._conn.fetchrow(
            f"UPDATE devices SET state = 'REVOKED', revoked_at = now(), revoked_by = $2, updated_at = now() "
            f"WHERE device_uuid = $1 AND state <> 'REVOKED' RETURNING {_DEVICE_COLUMNS}",
            device_uuid, revoked_by,
        )
        if row is None:
            raise InvalidTransition(f"{device_uuid}: already revoked or missing")
        return _device(row)

    async def set_node(
        self, device_uuid: str, *, node_id: str, node_hostname: str | None, node_ip: str | None
    ) -> Device:
        row = await self._conn.fetchrow(
            f"UPDATE devices SET node_id = $2, node_hostname = $3, node_ip = $4::inet, updated_at = now() "
            f"WHERE device_uuid = $1 RETURNING {_DEVICE_COLUMNS}",
            device_uuid, node_id, node_hostname, node_ip,
        )
        if row is None:
            raise InvalidTransition(f"{device_uuid}: missing")
        return _device(row)

    async def set_preauth(self, device_uuid: str, *, preauth_key_id: str, preauth_expires: datetime | None) -> Device:
        row = await self._conn.fetchrow(
            f"UPDATE devices SET preauth_key_id = $2, preauth_expires = $3, updated_at = now() "
            f"WHERE device_uuid = $1 AND state = 'CLAIMED' RETURNING {_DEVICE_COLUMNS}",
            device_uuid, preauth_key_id, preauth_expires,
        )
        if row is None:
            raise InvalidTransition(f"{device_uuid}: key reissue requires CLAIMED")
        return _device(row)

    async def set_cert_fingerprint(self, device_uuid: str, fingerprint: str) -> None:
        await self._conn.execute(
            "UPDATE devices SET cert_fingerprint = $2, updated_at = now() WHERE device_uuid = $1",
            device_uuid, fingerprint,
        )

    async def add_event(
        self,
        device_uuid: str,
        tenant_id: str,
        action: str,
        actor_sub: str,
        ip: str | None,
        details: dict[str, Any] | None,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO device_events (device_uuid, tenant_id, action, actor_sub, ip, details) "
            "VALUES ($1, $2, $3, $4, $5::inet, $6)",
            device_uuid, tenant_id, action, actor_sub, ip, details,
        )

    async def list_events(self, device_uuid: str) -> list[DeviceEvent]:
        rows = await self._conn.fetch(
            "SELECT id, device_uuid, tenant_id, action, actor_sub, ip, details, created_at "
            "FROM device_events WHERE device_uuid = $1 ORDER BY created_at, id",
            device_uuid,
        )
        return [_event(r) for r in rows]
