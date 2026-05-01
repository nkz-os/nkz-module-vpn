"""
Cliente para la API REST de Headscale.

Headscale es el plano de control. Este servicio es el ÚNICO autorizado a
llamar a su API. El entity-manager NO llama a Headscale directamente.

Referencia API: https://headscale.net/ref/api/
"""

import logging
from typing import Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

HEADSCALE_BASE = settings.HEADSCALE_API_URL.rstrip("/")
_HEADERS = {"Authorization": f"Bearer {settings.HEADSCALE_API_KEY}"}


async def _get(path: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{HEADSCALE_BASE}{path}", headers=_HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{HEADSCALE_BASE}{path}", json=body, headers=_HEADERS, timeout=10
        )
        r.raise_for_status()
        return r.json()


async def _delete(path: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{HEADSCALE_BASE}{path}", headers=_HEADERS, timeout=10)
        r.raise_for_status()


# =============================================================================
# Users (= tenants en Nekazari)
# =============================================================================

async def ensure_user_exists(tenant_id: str) -> dict:
    """
    Crea el user de Headscale para el tenant si no existe.
    Idempotente — si ya existe, lo devuelve sin error.
    """
    try:
        return await _get(f"/api/v1/user/{tenant_id}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.info("Creating Headscale user for tenant %s", tenant_id)
            result = await _post("/api/v1/user", {"name": tenant_id})
            logger.info(
                "Headscale user %s created. Add tag:tenant-%s to ACLs.",
                tenant_id, tenant_id,
            )
            return result
        raise


# =============================================================================
# Pre-Auth Keys (= tokens de activación para dispositivos)
# =============================================================================

async def create_preauth_key(
    tenant_id: str,
    expiration_minutes: int = 5,
    reusable: bool = False,
) -> str:
    """
    Genera una Pre-Auth Key efímera para que un dispositivo se una a la red SDN.
    Por defecto: 5 minutos de validez, un solo uso.
    """
    await ensure_user_exists(tenant_id)
    data = await _post(
        "/api/v1/preauthkey",
        {
            "user": tenant_id,
            "reusable": reusable,
            "ephemeral": False,
            "expiration": f"{expiration_minutes}m",
        },
    )
    key = data.get("preAuthKey", {}).get("key")
    if not key:
        raise ValueError(f"Headscale did not return a Pre-Auth Key: {data}")
    return key


# =============================================================================
# Peers / Nodes
# =============================================================================

async def list_peers(tenant_id: str) -> list[dict]:
    """Lista los nodos activos de un tenant en la red SDN."""
    data = await _get(f"/api/v1/node?user={tenant_id}")
    return data.get("nodes", [])


async def get_peer(node_id: str) -> Optional[dict]:
    """Devuelve un nodo por su ID, o None si no existe."""
    try:
        data = await _get(f"/api/v1/node/{node_id}")
        return data.get("node")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise


async def delete_peer(node_id: str) -> None:
    """
    Revoca un peer de la red SDN.
    Usar cuando un dispositivo se pierde, se vende, o se compromete.
    """
    logger.warning(f"Revoking Headscale peer {node_id}")
    await _delete(f"/api/v1/node/{node_id}")
