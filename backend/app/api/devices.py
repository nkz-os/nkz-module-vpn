"""
Tenant device routes (TenantAdmin / PlatformAdmin, behind the api-gateway).
The tenant always comes from the verified X-Tenant-ID, never from the body.
A device of another tenant answers 404, indistinguishable from a missing one.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.db.repo import DeviceRepo
from app.deps import Services, get_client_ip, get_services
from app.middleware import AuthContext, require_roles
from app.models import Device
from app.services import claim_flow
from app.services.headscale import HeadscaleError, Node

router = APIRouter(prefix="/devices", tags=["devices"])

_tenant_admin = require_roles("TenantAdmin", "PlatformAdmin")


class ValidateIn(BaseModel):
    device_uuid: UUID
    claim_code: str = Field(min_length=1, max_length=64)


class ClaimIn(ValidateIn):
    display_name: str | None = Field(default=None, max_length=128)


class ValidateOut(BaseModel):
    valid: bool
    device_uuid: str
    device_type: str
    display_name: str | None
    state: str


class NetworkOut(BaseModel):
    login_server: str
    preauth_key: str
    expires_at: datetime
    hostname: str


class ClaimOut(BaseModel):
    device_uuid: str
    device_type: str
    display_name: str | None
    state: str
    ngsi_entity_id: str
    network: NetworkOut | None  # robots and gateways only; the key is shown once


class NodeOut(BaseModel):
    online: bool
    last_seen: datetime | None
    ip: str | None


class DeviceOut(BaseModel):
    device_uuid: str
    tenant_id: str
    device_type: str
    display_name: str | None
    state: str
    ngsi_entity_id: str | None
    node: NodeOut | None
    network_unknown: bool = False  # Headscale could not be asked; `node: null` is then not "not joined"


class DeviceListOut(BaseModel):
    devices: list[DeviceOut]
    total: int


class DeviceEventOut(BaseModel):
    action: str
    actor_sub: str
    created_at: datetime
    details: dict | None


class DeviceEventsOut(BaseModel):
    events: list[DeviceEventOut]


def _device_out(device: Device, node: Node | None, unknown: bool = False) -> DeviceOut:
    return DeviceOut(
        device_uuid=device.device_uuid, tenant_id=device.tenant_id, device_type=device.device_type,
        display_name=device.display_name, state=device.state, ngsi_entity_id=device.ngsi_entity_id,
        node=NodeOut(online=node.online, last_seen=node.last_seen, ip=node.ip) if node else None,
        network_unknown=unknown,
    )


@router.post("/validate", response_model=ValidateOut)
async def validate_device(body: ValidateIn, request: Request, auth: AuthContext = Depends(_tenant_admin),
                          svc: Services = Depends(get_services)):
    device = await claim_flow.validate(svc, tenant_id=auth.tenant_id, device_uuid=str(body.device_uuid),
                                       claim_code=body.claim_code, actor=auth.user_id, ip=get_client_ip(request))
    return ValidateOut(valid=True, device_uuid=device.device_uuid, device_type=device.device_type,
                       display_name=device.display_name, state=device.state)


@router.post("/claim", response_model=ClaimOut)
async def claim_device(body: ClaimIn, request: Request, auth: AuthContext = Depends(_tenant_admin),
                       svc: Services = Depends(get_services)):
    result = await claim_flow.claim(svc, tenant_id=auth.tenant_id, device_uuid=str(body.device_uuid),
                                    claim_code=body.claim_code, display_name=body.display_name,
                                    actor=auth.user_id, ip=get_client_ip(request))
    device = result.device
    return ClaimOut(
        device_uuid=device.device_uuid, device_type=device.device_type, display_name=device.display_name,
        state=device.state, ngsi_entity_id=device.ngsi_entity_id,
        network=NetworkOut(login_server=svc.settings.headscale_public_url, preauth_key=result.preauth.key,
                           expires_at=result.preauth.expires_at, hostname=device.device_uuid)
        if result.preauth else None,
    )


@router.get("", response_model=DeviceListOut)
async def list_devices(all_tenants: bool = Query(False), auth: AuthContext = Depends(_tenant_admin),
                       svc: Services = Depends(get_services)):
    if all_tenants and not auth.has_role("PlatformAdmin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PlatformAdmin role required")
    scope = svc.db.platform_tx() if all_tenants else svc.db.tenant_tx(auth.tenant_id)
    async with scope as conn:
        devices = await DeviceRepo(conn).list_devices()
    nodes_by_user: dict[str, list[Node] | None] = {}
    out: list[DeviceOut] = []
    for device in devices:
        node, unknown = None, False
        if device.state == "CLAIMED" and device.headscale_user:
            if device.headscale_user not in nodes_by_user:
                try:
                    nodes_by_user[device.headscale_user] = await svc.headscale.list_nodes(device.headscale_user)
                except HeadscaleError:
                    nodes_by_user[device.headscale_user] = None
            nodes = nodes_by_user[device.headscale_user]
            if nodes is None:
                unknown = True
            else:
                view = await claim_flow.reconcile_node(svc, device, nodes)
                device, node = view.device, view.node
        out.append(_device_out(device, node, unknown))
    return DeviceListOut(devices=out, total=len(out))


async def _get_device(svc: Services, tenant_id: str, device_uuid: UUID) -> Device:
    async with svc.db.tenant_tx(tenant_id) as conn:
        device = await DeviceRepo(conn).get(str(device_uuid))
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


@router.get("/{device_uuid}", response_model=DeviceOut)
async def get_device(device_uuid: UUID, auth: AuthContext = Depends(_tenant_admin),
                     svc: Services = Depends(get_services)):
    device = await _get_device(svc, auth.tenant_id, device_uuid)
    view = await claim_flow.reconcile_node(svc, device)
    return _device_out(view.device, view.node, view.unknown)


@router.get("/{device_uuid}/events", response_model=DeviceEventsOut)
async def list_events(device_uuid: UUID, auth: AuthContext = Depends(_tenant_admin),
                      svc: Services = Depends(get_services)):
    await _get_device(svc, auth.tenant_id, device_uuid)
    async with svc.db.tenant_tx(auth.tenant_id) as conn:
        events = await DeviceRepo(conn).list_events(str(device_uuid))
    return DeviceEventsOut(events=[DeviceEventOut(action=e.action, actor_sub=e.actor_sub, created_at=e.created_at,
                                                  details=e.details) for e in events])


@router.delete("/{device_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(device_uuid: UUID, request: Request, auth: AuthContext = Depends(_tenant_admin),
                        svc: Services = Depends(get_services)):
    await claim_flow.revoke(svc, tenant_id=auth.tenant_id, device_uuid=str(device_uuid), actor=auth.user_id,
                            ip=get_client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{device_uuid}/reissue-key", response_model=NetworkOut)
async def reissue_key(device_uuid: UUID, request: Request, auth: AuthContext = Depends(_tenant_admin),
                      svc: Services = Depends(get_services)):
    preauth = await claim_flow.reissue_key(svc, tenant_id=auth.tenant_id, device_uuid=str(device_uuid),
                                           actor=auth.user_id, ip=get_client_ip(request))
    return NetworkOut(login_server=svc.settings.headscale_public_url, preauth_key=preauth.key,
                      expires_at=preauth.expires_at, hostname=str(device_uuid))
