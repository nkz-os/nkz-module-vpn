"""
Claim and revocation flows — the only code that moves a device between states.

Claim order (spec §3): rate limit -> lock the PENDING row -> check the code ->
Headscale user -> SDM twin (idempotent upsert) -> pre-auth key -> mark CLAIMED
-> commit. The key is created last among the remote effects, so an Orion
failure never leaves a usable key behind; if anything fails after the key
exists, the key is expired with the value still in memory. The device stays
PENDING on every failure, so a retry is always possible.
"""

import logging
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.db.repo import DeviceRepo
from app.deps import Services
from app.models import Device
from app.services.claim_code import factory_secret_for, validate_claim_code
from app.services.headscale import HeadscaleError, Node, PreAuthKey, headscale_user_for
from app.services.ratelimit import RateLimitUnavailable, check_all
from app.services.twin import TwinError, build_twin, twin_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimResult:
    device: Device
    preauth: PreAuthKey


def _http(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _check_state(device: Device | None) -> Device:
    if device is None:
        raise _http(status.HTTP_404_NOT_FOUND, "Device not found")
    if device.state == "CLAIMED":
        raise _http(status.HTTP_409_CONFLICT, "Device already activated")
    if device.state == "REVOKED":
        raise _http(status.HTTP_410_GONE, "Device has been revoked")
    return device


def _code_ok(svc: Services, device: Device, claim_code: str) -> bool:
    try:
        secret = factory_secret_for(svc.settings, device.claim_version)
    except ValueError:
        logger.error("factory secret version %s missing", device.claim_version,
                     extra={"device_uuid": device.device_uuid})
        raise _http(status.HTTP_500_INTERNAL_SERVER_ERROR, "Claim validation is not configured") from None
    return validate_claim_code(device.device_uuid, claim_code, secret, device.claim_version)


async def _rate_limit(svc: Services, *, tenant_id: str, device_uuid: str, ip: str | None) -> None:
    try:
        await check_all(svc.limiter, device_uuid=device_uuid, tenant_id=tenant_id, ip=ip, settings=svc.settings)
    except RateLimitUnavailable:
        logger.error("claim rate limiter unavailable — refusing claims", extra={"tenant_id": tenant_id})
        raise _http(status.HTTP_503_SERVICE_UNAVAILABLE, "Claims are temporarily unavailable") from None


async def _reject(svc: Services, *, tenant_id: str, device_uuid: str, actor: str, ip: str | None) -> HTTPException:
    async with svc.db.tenant_tx(tenant_id) as conn:
        await DeviceRepo(conn).add_event(device_uuid, tenant_id, "CLAIM_REJECTED", actor, ip, {"reason": "bad_code"})
    logger.warning("claim rejected", extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
    return _http(status.HTTP_400_BAD_REQUEST, "Invalid claim code")


async def validate(svc: Services, *, tenant_id: str, device_uuid: str, claim_code: str, actor: str,
                   ip: str | None) -> Device:
    await _rate_limit(svc, tenant_id=tenant_id, device_uuid=device_uuid, ip=ip)
    async with svc.db.tenant_tx(tenant_id) as conn:
        device = _check_state(await DeviceRepo(conn).get(device_uuid))
    if not _code_ok(svc, device, claim_code):
        raise await _reject(svc, tenant_id=tenant_id, device_uuid=device_uuid, actor=actor, ip=ip)
    return device


async def claim(svc: Services, *, tenant_id: str, device_uuid: str, claim_code: str, display_name: str | None,
                actor: str, ip: str | None) -> ClaimResult:
    await _rate_limit(svc, tenant_id=tenant_id, device_uuid=device_uuid, ip=ip)
    hs_user = headscale_user_for(tenant_id)
    preauth: PreAuthKey | None = None
    rejected = False
    try:
        async with svc.db.tenant_tx(tenant_id) as conn:
            repo = DeviceRepo(conn)
            device = _check_state(await repo.get_for_update(device_uuid))
            if not _code_ok(svc, device, claim_code):
                rejected = True
            else:
                entity_type, _ = twin_id(device.device_type, tenant_id, device_uuid)
                writer = svc.twin_writer(tenant_id)
                try:
                    await svc.headscale.ensure_user(hs_user)
                    entity_id = await writer.upsert(
                        build_twin(device.device_type, tenant_id, device_uuid, display_name or device.display_name))
                    preauth = await svc.headscale.create_preauth_key(hs_user, svc.settings.preauth_ttl_minutes)
                finally:
                    await writer.close()
                claimed = await repo.mark_claimed(
                    device_uuid, claimed_by=actor, headscale_user=hs_user, preauth_key_id=preauth.id,
                    preauth_expires=preauth.expires_at, ngsi_entity_id=entity_id, ngsi_entity_type=entity_type,
                    display_name=display_name,
                )
                await repo.add_event(device_uuid, tenant_id, "CLAIMED", actor, ip,
                                     {"preauth_key_id": preauth.id, "ngsi_entity_id": entity_id})
    except HTTPException:
        raise
    except (HeadscaleError, TwinError) as exc:
        await _expire_quietly(svc, hs_user, preauth, device_uuid)
        logger.error("claim failed: %s", exc, extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
        raise _http(status.HTTP_502_BAD_GATEWAY, "Device network provisioning failed, retry later") from None
    except Exception as exc:  # DB failure after remote effects: undo the key, report
        await _expire_quietly(svc, hs_user, preauth, device_uuid)
        logger.error("claim failed: %s", type(exc).__name__, extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
        raise _http(status.HTTP_502_BAD_GATEWAY, "Device activation failed, retry later") from None
    if rejected:
        raise await _reject(svc, tenant_id=tenant_id, device_uuid=device_uuid, actor=actor, ip=ip)
    logger.info("device claimed", extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
    return ClaimResult(device=claimed, preauth=preauth)


async def _expire_quietly(svc: Services, hs_user: str, preauth: PreAuthKey | None, device_uuid: str) -> None:
    if preauth is None:
        return
    try:
        await svc.headscale.expire_preauth_key(hs_user, preauth.key)
    except HeadscaleError as exc:
        logger.error("could not expire orphan pre-auth key %s: %s", preauth.id, exc, extra={"device_uuid": device_uuid})


async def reconcile_node(svc: Services, device: Device, nodes: list[Node] | None = None) -> tuple[Device, Node | None]:
    """Find the device's tailnet node; persist it the first time it is seen.

    Headscale being unreachable degrades to "no node" (the registry stays readable).
    """
    if device.state != "CLAIMED" or not device.headscale_user:
        return device, None
    try:
        if nodes is None:
            nodes = await svc.headscale.list_nodes(device.headscale_user)
    except HeadscaleError as exc:
        logger.warning("node lookup failed: %s", exc, extra={"device_uuid": device.device_uuid})
        return device, None
    node = next((n for n in nodes if device.node_id and n.id == device.node_id), None)
    node = node or next((n for n in nodes if device.preauth_key_id and n.preauth_key_id == device.preauth_key_id), None)
    node = node or next((n for n in nodes if device.device_uuid in (n.given_name, n.hostname)), None)
    if node and node.id != device.node_id:
        async with svc.db.tenant_tx(device.tenant_id) as conn:
            repo = DeviceRepo(conn)
            device = await repo.set_node(device.device_uuid, node_id=node.id, node_hostname=node.given_name or
                                         node.hostname, node_ip=node.ip)
            await repo.add_event(device.device_uuid, device.tenant_id, "NODE_SEEN", "system", None,
                                 {"node_id": node.id})
    return device, node


async def revoke(svc: Services, *, tenant_id: str, device_uuid: str, actor: str, ip: str | None) -> None:
    async with svc.db.tenant_tx(tenant_id) as conn:
        device = await DeviceRepo(conn).get(device_uuid)
    if device is None:
        raise _http(status.HTTP_404_NOT_FOUND, "Device not found")
    if device.state == "REVOKED":
        raise _http(status.HTTP_409_CONFLICT, "Device already revoked")

    details: dict[str, str] = {}
    if device.state == "CLAIMED":
        # Network access first: if the node cannot be removed, nothing changes.
        _, node = await reconcile_node(svc, device)
        node_id = node.id if node else device.node_id
        if node_id:
            try:
                await svc.headscale.delete_node(node_id)
            except HeadscaleError as exc:
                logger.error("node delete failed: %s", exc, extra={"device_uuid": device_uuid})
                raise _http(status.HTTP_502_BAD_GATEWAY, "Could not remove the device from the network") from None
            details["node_id"] = node_id
        if device.ngsi_entity_id:
            writer = svc.twin_writer(tenant_id)
            try:
                await writer.mark_revoked(device.ngsi_entity_id)
                details["twin"] = "revoked"
            except TwinError as exc:  # the twin is metadata; revocation must not depend on it
                logger.error("twin revoke failed: %s", exc, extra={"device_uuid": device_uuid})
                details["twin"] = "sync_failed"
            finally:
                await writer.close()

    async with svc.db.tenant_tx(tenant_id) as conn:
        repo = DeviceRepo(conn)
        await repo.mark_revoked(device_uuid, revoked_by=actor)
        await repo.add_event(device_uuid, tenant_id, "REVOKED", actor, ip, details or None)
    logger.info("device revoked", extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
