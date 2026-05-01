"""
Endpoints de fábrica — solo accesibles con rol 'Factory' o 'PlatformAdmin'.

Flujo de fábrica para KLinux (rover / gateway):
    1. factory_tool.py genera keypair + CSR localmente.
    2. POST /factory/sign-csr → devuelve certificado X.509 firmado.
    3. POST /factory/register-device → crea el registro en BD + devuelve Claim Code.
    4. Imprimir Claim Code en el chasis. Flashear cert+key en el dispositivo.

Flujo de fábrica para ESP32 (sensor):
    1. factory_tool.py genera keypair + CSR.
    2. POST /factory/sign-csr → devuelve certificado.
    3. POST /factory/register-device → crea registro + devuelve Claim Code.
    4. Incrustar cert+key en partición NVS via PlatformIO/ESP-IDF.
    5. Imprimir Claim Code en el chasis.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.middleware.auth import require_factory_role
from app.models import ProvisionedDevice
from app.services import claim_code as cc_service
from app.services import pki as pki_service
from app.services import audit as audit_service
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/factory", tags=["Factory"])

ALLOWED_DEVICE_TYPES = {"rover", "gateway", "sensor_esp32"}


class SignCsrRequest(BaseModel):
    csr_pem: str
    device_uuid: str
    device_type: str


class SignCsrResponse(BaseModel):
    certificate_pem: str


class RegisterDeviceRequest(BaseModel):
    device_uuid: str
    device_type: str
    tenant_id: str
    device_name: str | None = None


class RegisterDeviceResponse(BaseModel):
    claim_code: str       # Imprimir en el chasis: "V1-NKZ8492X"
    device_uuid: str
    device_type: str


@router.post(
    "/sign-csr",
    response_model=SignCsrResponse,
    summary="Firma un CSR con la CA IoT (solo fábrica)",
)
async def sign_csr(
    req: SignCsrRequest,
    _payload: dict = Depends(require_factory_role),
):
    """
    Firma el CSR del dispositivo con la CA IoT de Nekazari.
    El certificado resultante se incrusta en el firmware del dispositivo.
    """
    if req.device_type not in ALLOWED_DEVICE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid device_type. Allowed: {ALLOWED_DEVICE_TYPES}",
        )

    try:
        cert_pem = await pki_service.sign_csr(
            req.csr_pem, req.device_uuid, req.device_type
        )
    except (RuntimeError, TimeoutError) as e:
        logger.error(f"CSR signing failed for {req.device_uuid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Certificate signing failed: {e}",
        )

    return SignCsrResponse(certificate_pem=cert_pem)


@router.post(
    "/register-device",
    response_model=RegisterDeviceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Pre-registra un dispositivo y genera su Claim Code (solo fábrica)",
)
async def register_device(
    req: RegisterDeviceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _payload: dict = Depends(require_factory_role),
):
    """
    Registra el dispositivo en BD con estado PENDING y devuelve el Claim Code.
    El Claim Code se imprime en el chasis — es el único mecanismo de activación.
    """
    if req.device_type not in ALLOWED_DEVICE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid device_type. Allowed: {ALLOWED_DEVICE_TYPES}",
        )

    # Comprobar que el UUID no esté ya registrado
    existing = await db.get(ProvisionedDevice, req.device_uuid)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device {req.device_uuid} already registered",
        )

    version = settings.FACTORY_SECRET_CURRENT_VERSION
    factory_secret = cc_service.get_factory_secret_for_version(version, settings)

    # Generar el código (para imprimir) y su hash (para almacenar)
    claim_code = cc_service.generate_claim_code(req.device_uuid, factory_secret, version)
    claim_hash = cc_service.generate_claim_hash(req.device_uuid, factory_secret, version)

    device = ProvisionedDevice(
        uuid=req.device_uuid,
        tenant_id=req.tenant_id,
        device_type=req.device_type,
        device_name=req.device_name,
        claim_code_hash=claim_hash,
        claim_version=version,
        state="PENDING",
    )
    db.add(device)

    # Audit log
    actor_sub = _payload.get("sub", "unknown")
    await audit_service.log_event(
        db, tenant_id=req.tenant_id, device_uuid=req.device_uuid,
        action="REGISTERED", actor_sub=actor_sub, ip_address=None,
    )

    logger.info(f"Device {req.device_uuid} ({req.device_type}) registered for tenant {req.tenant_id}")

    return RegisterDeviceResponse(
        claim_code=claim_code,
        device_uuid=req.device_uuid,
        device_type=req.device_type,
    )
