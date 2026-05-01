"""
Endpoints ZTP (Zero-Touch Provisioning) para activación de dispositivos.

Flujo de activación desde la UI del Tenant Admin:
    1. Admin introduce nombre del dispositivo + Claim Code (impreso en el chasis).
    2. POST /devices/claim → valida HMAC, genera Pre-Auth Key en Headscale,
       crea entidad NGSI-LD en entity-manager, marca device como CONSUMED.
    3. El dispositivo (KLinux) se enciende y ejecuta:
           tailscale up --login-server=https://vpn.YOUR_DOMAIN --authkey=<KEY>
    4. Headscale registra el peer. El dispositivo está en línea.
    5. GET /devices/{uuid}/status → devuelve estado Headscale en tiempo real.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.middleware.auth import require_auth, get_tenant_id
from app.models import ProvisionedDevice, DEVICE_TYPE_TO_NGSI_TYPE
from app.services import claim_code as cc_service
from app.services import headscale as hs_service
from app.services import entity_manager as em_service
from app.services import tenant_limits as tl_service
from app.config import settings
from app.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/devices", tags=["Devices"])


class ClaimRequest(BaseModel):
    device_uuid: str
    claim_code: str     # "V1-NKZ8492X" — introducido por el Tenant Admin
    device_name: str | None = None


class ClaimResponse(BaseModel):
    device_uuid: str
    device_type: str
    device_name: str | None
    preauth_key: str | None         # None para ESP32 (no usan Tailscale)
    login_server: str | None        # Headscale public URL for `tailscale up --login-server`
    ngsi_entity_id: str | None
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


@router.get(
    "/",
    response_model=DeviceListResponse,
    summary="Lista todos los dispositivos del tenant",
)
async def list_devices(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    result = await db.execute(
        select(ProvisionedDevice)
        .where(ProvisionedDevice.tenant_id == tenant_id)
        .order_by(ProvisionedDevice.created_at.desc())
    )
    devices = result.scalars().all()
    return DeviceListResponse(
        devices=[
            DeviceStatusResponse(
                device_uuid=d.uuid,
                device_type=d.device_type,
                device_name=d.device_name,
                state=d.state,
                headscale_peer_id=d.headscale_peer_id,
                online=False,   # real-time status via /devices/{uuid}/status
                last_seen=None,
            )
            for d in devices
        ],
        total=len(devices),
    )


@router.post(
    "/claim",
    response_model=ClaimResponse,
    summary="Activa un dispositivo con su Claim Code",
)
async def claim_device(
    req: ClaimRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Valida el Claim Code e inicia el provisioning del dispositivo.

    Para KLinux (rover/gateway): genera Pre-Auth Key de Headscale (5 min validez).
    Para ESP32: solo valida el código y marca como CONSUMED (se conecta via mTLS).
    """
    # Rate limiting: per-tenant (5/h) + per-IP (10/h)
    tenant_key = f"rate:claim:tenant:{tenant_id}"
    ip = request.client.host if request.client else "unknown"
    ip_key = f"rate:claim:ip:{ip}"

    if not await limiter.check(
        tenant_key,
        settings.CLAIM_RATE_LIMIT_ATTEMPTS,
        settings.CLAIM_RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many claim attempts for this tenant. Try again later.",
        )
    if not await limiter.check(
        ip_key,
        10,
        settings.CLAIM_RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many claim attempts from this IP. Try again later.",
        )

    device = await db.get(ProvisionedDevice, req.device_uuid)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    # El dispositivo debe pertenecer al tenant del token
    if device.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device does not belong to your tenant",
        )

    if device.state == "CONSUMED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Device already activated",
        )

    if device.state == "REVOKED":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Device has been revoked",
        )

    # Validar Claim Code (timing-safe)
    factory_secret = cc_service.get_factory_secret_for_version(
        device.claim_version, settings
    )
    if not cc_service.validate_claim_code(
        req.device_uuid, req.claim_code, device.claim_code_hash,
        factory_secret, device.claim_version,
    ):
        logger.warning(f"Invalid claim code attempt for device {req.device_uuid} by tenant {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid claim code",
        )

    # Quota check: enforce max_devices per tenant
    active_count = await tl_service.count_active_devices(db, tenant_id)
    max_devices = await tl_service.get_max_devices(db, tenant_id)
    if active_count >= max_devices:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Device quota exceeded ({active_count}/{max_devices})",
        )

    # Nombre del dispositivo (del request o conservar el de fábrica)
    if req.device_name:
        device.device_name = req.device_name

    preauth_key = None

    # Para KLinux: generar Pre-Auth Key de Headscale (5 min, un solo uso)
    if device.device_type in ("rover", "gateway"):
        preauth_key = await hs_service.create_preauth_key(
            tenant_id=tenant_id,
            expiration_minutes=5,
            reusable=False,
        )

    # SOTA Type Mapping — from canonical source in models.py
    ngsi_type = DEVICE_TYPE_TO_NGSI_TYPE.get(device.device_type, "Device")
    ngsi_entity_id = f"urn:ngsi-ld:{ngsi_type}:{device.uuid}"

    # Marcar como CONSUMED
    device.state = "CONSUMED"
    device.ngsi_entity_id = ngsi_entity_id
    device.provisioned_at = datetime.now(timezone.utc)

    logger.info(
        "Device %s (%s) claimed by tenant %s", device.uuid, device.device_type, tenant_id
    )

    # Crear entidad NGSI-LD en entity-manager (best-effort — no bloquea si falla)
    raw_token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    try:
        await em_service.create_ngsi_entity(
            token=raw_token,
            entity_id=ngsi_entity_id,
            entity_type=ngsi_type,
            device_uuid=device.uuid,
            device_name=device.device_name,
            device_type=device.device_type,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.warning(
            "Entity %s could not be created in entity-manager: %s — "
            "create it manually via the platform UI.",
            ngsi_entity_id, exc,
        )

    return ClaimResponse(
        device_uuid=device.uuid,
        device_type=device.device_type,
        device_name=device.device_name,
        preauth_key=preauth_key,
        login_server=settings.HEADSCALE_PUBLIC_URL or None,
        ngsi_entity_id=ngsi_entity_id,
        state=device.state,
    )


@router.get(
    "/{device_uuid}/status",
    response_model=DeviceStatusResponse,
    summary="Estado de un dispositivo (Headscale + BD)",
)
async def device_status(
    device_uuid: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    device = await db.get(ProvisionedDevice, device_uuid)
    if not device or device.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    online = False
    last_seen = None

    # Consultar Headscale para el estado en tiempo real (solo KLinux)
    if device.headscale_peer_id:
        peer = await hs_service.get_peer(device.headscale_peer_id)
        if peer:
            last_seen_ts = peer.get("lastSeen")
            online = peer.get("online", False)
            last_seen = last_seen_ts

    return DeviceStatusResponse(
        device_uuid=device.uuid,
        device_type=device.device_type,
        device_name=device.device_name,
        state=device.state,
        headscale_peer_id=device.headscale_peer_id,
        online=online,
        last_seen=last_seen,
    )


@router.delete(
    "/{device_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoca un dispositivo",
)
async def revoke_device(
    device_uuid: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Revoca el dispositivo: lo elimina de Headscale (si procede) y lo marca REVOKED en BD.
    Usar cuando el dispositivo se pierde, se vende o se sospecha compromiso.
    """
    device = await db.get(ProvisionedDevice, device_uuid)
    if not device or device.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    if device.headscale_peer_id:
        try:
            await hs_service.delete_peer(device.headscale_peer_id)
        except Exception as e:
            logger.error(f"Failed to delete Headscale peer for {device_uuid}: {e}")

    device.state = "REVOKED"
    logger.warning(f"Device {device_uuid} revoked by tenant {tenant_id}")
