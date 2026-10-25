"""
Factory routes (PlatformAdmin): register a device for a tenant and sign its
certificate. They run in the platform RLS scope because a factory operator
acts across tenants. Reached through the api-gateway — from the web factory
panel or from factory-tool/flash_tool.py with a PlatformAdmin bearer token.
"""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.db.repo import DeviceExists, DeviceRepo
from app.deps import Services, get_client_ip, get_services
from app.middleware import AuthContext, require_roles
from app.services.claim_code import factory_secret_for, generate_claim_code
from app.services.pki import PkiError, fingerprint_sha256, validate_csr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/factory", tags=["factory"])

TENANT_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"  # same rule as the gateway's X-Tenant-ID


class RegisterDeviceIn(BaseModel):
    device_uuid: UUID
    device_type: Literal["rover", "gateway", "sensor"]
    tenant_id: str = Field(min_length=3, max_length=63, pattern=TENANT_PATTERN)
    display_name: str | None = Field(default=None, max_length=128)


class RegisterDeviceOut(BaseModel):
    device_uuid: str
    device_type: str
    tenant_id: str
    claim_code: str


class SignCsrIn(BaseModel):
    csr_pem: str = Field(max_length=16384)
    device_uuid: UUID


class SignCsrOut(BaseModel):
    certificate_pem: str
    ca_pem: str


@router.post("/register-device", response_model=RegisterDeviceOut, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: RegisterDeviceIn,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_roles("PlatformAdmin")),
    svc: Services = Depends(get_services),
):
    device_uuid = str(body.device_uuid)
    version = svc.settings.factory_secret_current_version
    try:
        secret = factory_secret_for(svc.settings, version)
    except ValueError:
        logger.error("factory secret for current version %s is not configured", version)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Factory signing is not configured") from None
    claim_code = generate_claim_code(device_uuid, secret, version)
    async with svc.db.platform_tx() as conn:
        repo = DeviceRepo(conn)
        existing = await repo.get(device_uuid)
        if existing is not None:
            # Same device again (e.g. the station lost the code when signing failed):
            # the code is deterministic, so hand it back. Anything else is a conflict.
            same = (existing.state == "PENDING" and existing.tenant_id == body.tenant_id
                    and existing.device_type == body.device_type)
            if not same:
                raise HTTPException(status.HTTP_409_CONFLICT, "Device already registered")
            again = factory_secret_for(svc.settings, existing.claim_version)
            response.status_code = status.HTTP_200_OK
            return RegisterDeviceOut(device_uuid=device_uuid, device_type=existing.device_type,
                                     tenant_id=existing.tenant_id,
                                     claim_code=generate_claim_code(device_uuid, again, existing.claim_version))
        try:
            await repo.create_pending(device_uuid, body.tenant_id, body.device_type, body.display_name, version)
        except DeviceExists:
            raise HTTPException(status.HTTP_409_CONFLICT, "Device already registered") from None
        await repo.add_event(device_uuid, body.tenant_id, "REGISTERED", auth.user_id, get_client_ip(request),
                             {"device_type": body.device_type, "claim_version": version})
    logger.info("device registered", extra={"device_uuid": device_uuid, "tenant_id": body.tenant_id,
                                            "device_type": body.device_type})
    return RegisterDeviceOut(device_uuid=device_uuid, device_type=body.device_type,
                             tenant_id=body.tenant_id, claim_code=claim_code)


@router.post("/sign-csr", response_model=SignCsrOut)
async def sign_csr(
    body: SignCsrIn,
    request: Request,
    auth: AuthContext = Depends(require_roles("PlatformAdmin")),
    svc: Services = Depends(get_services),
):
    device_uuid = str(body.device_uuid)
    async with svc.db.platform_tx() as conn:
        device = await DeviceRepo(conn).get(device_uuid)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not registered")
    if device.state == "REVOKED":
        raise HTTPException(status.HTTP_410_GONE, "Device has been revoked")
    try:
        validate_csr(body.csr_pem, device_uuid, device.device_type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    try:
        signed = await svc.pki.sign_csr(body.csr_pem, device_uuid, device.device_type)
    except PkiError as exc:
        logger.error("certificate signing failed: %s", exc, extra={"device_uuid": device_uuid})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Certificate signing failed") from None
    async with svc.db.platform_tx() as conn:
        repo = DeviceRepo(conn)
        await repo.set_cert_fingerprint(device_uuid, fingerprint_sha256(signed.certificate_pem))
        await repo.add_event(device_uuid, device.tenant_id, "CERT_SIGNED", auth.user_id,
                             get_client_ip(request), None)
    return SignCsrOut(certificate_pem=signed.certificate_pem, ca_pem=signed.ca_pem)
