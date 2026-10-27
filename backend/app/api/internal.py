"""
Device Management Backend - Internal Routes

Called by other in-cluster services (robotics), never by the browser: these
routes bypass the api-gateway and carry no gateway headers. They authenticate
with X-Internal-Service-Secret (constant-time compare), and read in the
platform scope because the caller states which device it asks about.

Robotics uses the lookup before enrolling a robot: the device must be CLAIMED,
be a rover and belong to the tenant the robotics request is for.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.devices import NodeOut
from app.db.repo import DeviceRepo
from app.deps import Services, get_services
from app.middleware import verify_internal_secret
from app.services import claim_flow

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_secret)])


class InternalDeviceOut(BaseModel):
    device_uuid: str
    tenant_id: str
    device_type: str
    state: str
    ngsi_entity_id: str | None
    ngsi_entity_type: str | None
    node: NodeOut | None


@router.get("/devices/{device_uuid}", response_model=InternalDeviceOut)
async def get_device(device_uuid: UUID, svc: Services = Depends(get_services)):
    async with svc.db.platform_tx() as conn:
        device = await DeviceRepo(conn).get(str(device_uuid))
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    view = await claim_flow.reconcile_node(svc, device)
    device, node = view.device, view.node
    return InternalDeviceOut(
        device_uuid=device.device_uuid, tenant_id=device.tenant_id, device_type=device.device_type,
        state=device.state, ngsi_entity_id=device.ngsi_entity_id, ngsi_entity_type=device.ngsi_entity_type,
        node=NodeOut(online=node.online, last_seen=node.last_seen, ip=node.ip) if node else None,
    )
