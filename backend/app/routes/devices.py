"""
Endpoints ZTP (Zero-Touch Provisioning) para activación de dispositivos.
Refactorizado para usar Orion-LD como fuente de verdad.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.middleware.auth import require_auth, get_tenant_id
from app.models import DEVICE_TYPE_TO_NGSI_TYPE
from app.services import claim_code as cc_service
from app.services import headscale as hs_service
from app.config import settings
from app.middleware.rate_limit import limiter

# Mock OrionClient import for now. nkz-platform-sdk should provide it.
try:
    from nkz_platform_sdk.clients import OrionClient
except ImportError:
    class OrionClient:
        def __init__(self, tenant_id: str): pass
        async def get_entities(self, type: str, q: str = None): return []
        async def get_entity(self, entity_id: str): return None
        async def update_entity_attrs(self, entity_id: str, attrs: dict): pass

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/devices", tags=["Devices"])


class ClaimRequest(BaseModel):
    device_uuid: str
    claim_code: str
    device_name: str | None = None


class ClaimResponse(BaseModel):
    device_uuid: str
    device_type: str
    device_name: str | None
    preauth_key: str | None
    login_server: str | None
    ngsi_entity_id: str | None
    state: str


class ValidateRequest(BaseModel):
    device_uuid: str
    claim_code: str


class ValidateResponse(BaseModel):
    valid: bool
    device_uuid: str
    device_type: str
    device_name: str | None
    state: str


class DeviceStatusResponse(BaseModel):
    device_uuid: str
    device_type: str
    device_name: str | None
    state: str
    headscale_peer_id: str | None
    online: bool
    last_seen: str | None


class DeviceListResponse(BaseModel):
    devices: list[DeviceStatusResponse]
    total: int
    max_devices: int = 50


async def _get_device_entity(orion: OrionClient, device_uuid: str):
    """Búsqueda de dispositivo en Orion-LD por deviceUUID."""
    types = ",".join(DEVICE_TYPE_TO_NGSI_TYPE.values())
    entities = await orion.get_entities(type=types, q=f"deviceUUID=={device_uuid}")
    if not entities:
        return None
    return entities[0]


@router.get("/", response_model=DeviceListResponse, summary="Lista todos los dispositivos del tenant")
async def list_devices(
    request: Request,
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    orion = OrionClient(tenant_id)
    types = ",".join(DEVICE_TYPE_TO_NGSI_TYPE.values())
    entities = await orion.get_entities(type=types)
    
    devices = []
    for ent in entities:
        props = ent.get("deviceState", {}).get("value", "PENDING")
        devices.append(
            DeviceStatusResponse(
                device_uuid=ent.get("deviceUUID", {}).get("value", ""),
                device_type=ent.get("deviceType", {}).get("value", "unknown"),
                device_name=ent.get("name", {}).get("value", None),
                state=ent.get("deviceState", {}).get("value", "PENDING"),
                headscale_peer_id=ent.get("headscalePeerId", {}).get("value", None),
                online=False,
                last_seen=None,
            )
        )
    return DeviceListResponse(devices=devices, total=len(devices), max_devices=50)


@router.post("/claim", response_model=ClaimResponse)
async def claim_device(
    req: ClaimRequest,
    request: Request,
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    tenant_key = f"rate:claim:tenant:{tenant_id}"
    ip = request.client.host if request.client else "unknown"
    ip_key = f"rate:claim:ip:{ip}"

    if not await limiter.check(tenant_key, settings.CLAIM_RATE_LIMIT_ATTEMPTS, settings.CLAIM_RATE_LIMIT_WINDOW_SECONDS):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many claim attempts")
    if not await limiter.check(ip_key, 10, settings.CLAIM_RATE_LIMIT_WINDOW_SECONDS):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many claim attempts from this IP")

    orion = OrionClient(tenant_id)
    entity = await _get_device_entity(orion, req.device_uuid)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    device_state = entity.get("deviceState", {}).get("value", "PENDING")
    if device_state == "CONSUMED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already activated")
    if device_state == "REVOKED":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Device has been revoked")

    claim_hash = entity.get("claimCodeHash", {}).get("value")
    claim_version = entity.get("claimVersion", {}).get("value", 1)

    factory_secret = cc_service.get_factory_secret_for_version(claim_version, settings)
    if not cc_service.validate_claim_code(req.device_uuid, req.claim_code, claim_hash, factory_secret, claim_version):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid claim code")

    device_type = entity.get("deviceType", {}).get("value", "unknown")
    preauth_key = None
    if device_type in ("rover", "gateway"):
        preauth_key = await hs_service.create_preauth_key(tenant_id=tenant_id, expiration_minutes=5, reusable=False)

    updates = {
        "deviceState": {"type": "Property", "value": "CONSUMED"},
        "provisionedAt": {"type": "Property", "value": datetime.now(timezone.utc).isoformat()}
    }
    if req.device_name:
        updates["name"] = {"type": "Property", "value": req.device_name}

    await orion.update_entity_attrs(entity["id"], updates)

    return ClaimResponse(
        device_uuid=req.device_uuid,
        device_type=device_type,
        device_name=req.device_name or entity.get("name", {}).get("value"),
        preauth_key=preauth_key,
        login_server=settings.HEADSCALE_PUBLIC_URL or None,
        ngsi_entity_id=entity["id"],
        state="CONSUMED",
    )


@router.post("/validate", response_model=ValidateResponse)
async def validate_device(
    req: ValidateRequest,
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    orion = OrionClient(tenant_id)
    entity = await _get_device_entity(orion, req.device_uuid)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    device_state = entity.get("deviceState", {}).get("value", "PENDING")
    if device_state == "CONSUMED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already activated")
    if device_state == "REVOKED":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Device has been revoked")

    claim_hash = entity.get("claimCodeHash", {}).get("value")
    claim_version = entity.get("claimVersion", {}).get("value", 1)
    factory_secret = cc_service.get_factory_secret_for_version(claim_version, settings)

    if not cc_service.validate_claim_code(req.device_uuid, req.claim_code, claim_hash, factory_secret, claim_version):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid claim code")

    return ValidateResponse(
        valid=True,
        device_uuid=req.device_uuid,
        device_type=entity.get("deviceType", {}).get("value", "unknown"),
        device_name=entity.get("name", {}).get("value"),
        state=device_state,
    )


@router.get("/{device_uuid}/status", response_model=DeviceStatusResponse)
async def device_status(
    device_uuid: str,
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    orion = OrionClient(tenant_id)
    entity = await _get_device_entity(orion, device_uuid)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    headscale_peer_id = entity.get("headscalePeerId", {}).get("value")
    online = False
    last_seen = None

    if headscale_peer_id:
        peer = await hs_service.get_peer(headscale_peer_id)
        if peer:
            last_seen = peer.get("lastSeen")
            online = peer.get("online", False)

    return DeviceStatusResponse(
        device_uuid=device_uuid,
        device_type=entity.get("deviceType", {}).get("value", "unknown"),
        device_name=entity.get("name", {}).get("value"),
        state=entity.get("deviceState", {}).get("value", "PENDING"),
        headscale_peer_id=headscale_peer_id,
        online=online,
        last_seen=last_seen,
    )


@router.delete("/{device_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    device_uuid: str,
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    orion = OrionClient(tenant_id)
    entity = await _get_device_entity(orion, device_uuid)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    headscale_peer_id = entity.get("headscalePeerId", {}).get("value")
    if headscale_peer_id:
        try:
            await hs_service.delete_peer(headscale_peer_id)
        except Exception as e:
            logger.error(f"Failed to delete Headscale peer: {e}")

    await orion.update_entity_attrs(entity["id"], {
        "deviceState": {"type": "Property", "value": "REVOKED"}
    })
