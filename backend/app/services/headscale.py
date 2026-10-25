"""
Headscale (v0.23) REST client — the only caller of the Headscale API.

The REST API is a grpc-gateway over the gRPC service: JSON fields are
lowerCamelCase and uint64 ids arrive as strings. Pre-auth keys carry the ACL
tag the device must hold (tag:field-device); Headscale applies it as a forced
tag when the node registers, which is what the tailnet policy matches on.

Errors never include request bodies: a pre-auth key must not reach a log line.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

FIELD_DEVICE_TAG = "tag:field-device"


def headscale_user_for(tenant_id: str) -> str:
    """Headscale user names are DNS labels: no underscores, lowercase."""
    return tenant_id.lower().replace("_", "-")


@dataclass(frozen=True)
class PreAuthKey:
    id: str
    key: str
    expires_at: datetime


@dataclass(frozen=True)
class KeyInfo:
    id: str
    key: str
    used: bool


@dataclass(frozen=True)
class Node:
    id: str
    hostname: str
    given_name: str
    ip: str | None
    online: bool
    last_seen: datetime | None
    preauth_key_id: str | None
    forced_tags: tuple[str, ...]


class HeadscaleError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _node(raw: dict[str, Any]) -> Node:
    ips = raw.get("ipAddresses") or []
    ipv4 = next((ip for ip in ips if ":" not in ip), ips[0] if ips else None)
    return Node(
        id=str(raw.get("id", "")),
        hostname=raw.get("name", ""),
        given_name=raw.get("givenName", ""),
        ip=ipv4,
        online=bool(raw.get("online", False)),
        last_seen=_parse_time(raw.get("lastSeen")),
        preauth_key_id=str((raw.get("preAuthKey") or {}).get("id") or "") or None,
        forced_tags=tuple(raw.get("forcedTags") or ()),
    )


class HeadscaleClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise HeadscaleError(f"headscale {method} {path}: {type(exc).__name__}") from None
        if resp.status_code >= 400:
            raise HeadscaleError(f"headscale {method} {path}: HTTP {resp.status_code}", resp.status_code)
        return resp.json() if resp.content else {}

    async def ensure_user(self, name: str) -> None:
        users = (await self._request("GET", "/api/v1/user")).get("users") or []
        if any(u.get("name") == name for u in users):
            return
        await self._request("POST", "/api/v1/user", json={"name": name})

    async def create_preauth_key(
        self, user: str, ttl_minutes: int, tags: tuple[str, ...] = (FIELD_DEVICE_TAG,)
    ) -> PreAuthKey:
        expiration = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        data = await self._request("POST", "/api/v1/preauthkey", json={
            "user": user,
            "reusable": False,
            "ephemeral": False,
            "expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "aclTags": list(tags),
        })
        raw = data.get("preAuthKey") or {}
        if not raw.get("key") or not raw.get("id"):
            raise HeadscaleError("headscale returned no pre-auth key")
        expires_at = _parse_time(raw.get("expiration")) or expiration
        return PreAuthKey(id=str(raw["id"]), key=raw["key"], expires_at=expires_at)

    async def expire_preauth_key(self, user: str, key: str) -> None:
        await self._request("POST", "/api/v1/preauthkey/expire", json={"user": user, "key": key})

    async def list_preauth_keys(self, user: str) -> list[KeyInfo]:
        data = await self._request("GET", "/api/v1/preauthkey", params={"user": user})
        return [KeyInfo(id=str(k.get("id", "")), key=k.get("key", ""), used=bool(k.get("used", False)))
                for k in data.get("preAuthKeys") or []]

    async def expire_unused_key(self, user: str, key_id: str) -> bool:
        """Expire the pre-auth key with this id if it was never used. True if expired."""
        for info in await self.list_preauth_keys(user):
            if info.id == key_id and not info.used and info.key:
                await self.expire_preauth_key(user, info.key)
                return True
        return False

    async def list_nodes(self, user: str) -> list[Node]:
        data = await self._request("GET", "/api/v1/node", params={"user": user})
        return [_node(n) for n in data.get("nodes") or []]

    async def find_node(self, user: str, *, preauth_key_id: str | None, hostname: str) -> Node | None:
        nodes = await self.list_nodes(user)
        if preauth_key_id:
            for node in nodes:
                if node.preauth_key_id == preauth_key_id:
                    return node
        for node in nodes:
            if hostname in (node.given_name, node.hostname):
                return node
        return None

    async def delete_node(self, node_id: str) -> None:
        await self._request("DELETE", f"/api/v1/node/{node_id}")
