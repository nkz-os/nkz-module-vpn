"""
Endpoints de consulta de peers SDN para el frontend.

DEPRECATED (2026-05-02): El módulo de connectivity fue eliminado (2026-03-23).
Este endpoint se conserva para uso futuro del módulo de robótica (ROS2/Zenoh).
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.middleware.auth import require_auth, get_tenant_id
from app.services import headscale as hs_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/peers", tags=["Peers"])


class PeerSummary(BaseModel):
    node_id: str
    hostname: str
    tailscale_ip: str | None
    online: bool
    last_seen: str | None


@router.get(
    "",
    response_model=list[PeerSummary],
    summary="Lista peers Headscale activos del tenant",
)
async def list_peers(
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Devuelve los peers de Headscale del tenant actual.
    Usado por el módulo connectivity para el panel de estado SDN.
    """
    try:
        nodes = await hs_service.list_peers(tenant_id)
    except Exception as e:
        logger.error(f"Failed to list Headscale peers for {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to reach Headscale API",
        )

    return [
        PeerSummary(
            node_id=str(n.get("id", "")),
            hostname=n.get("name", ""),
            tailscale_ip=n.get("ipAddresses", [None])[0],
            online=n.get("online", False),
            last_seen=n.get("lastSeen"),
        )
        for n in nodes
    ]
