"""
Claim and revocation flows — the only code that moves a device between states.

Claim order (spec §3): rate limit -> lock the PENDING row -> check the code ->
Headscale user -> SDM twin (idempotent upsert) -> pre-auth key (robots and
gateways only) -> mark CLAIMED -> commit. The key is created last among the
remote effects, so an Orion failure never leaves a usable key behind; if
anything fails after the key exists, the key is expired with the value still in
memory, and a twin created by this attempt is removed. The device stays PENDING
on every failure, so a retry is always possible.

Revocation takes the network away first: with the row locked it lists the
tenant's nodes, removes the device's node and expires its key if still unused.
If Headscale cannot answer, nothing changes (502).
"""

import logging
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.db.repo import DeviceRepo, InvalidTransition
from app.deps import Services
from app.models import Device
from app.services.claim_code import factory_secret_for, validate_claim_code
from app.services.headscale import HeadscaleError, Node, PreAuthKey, headscale_user_for
from app.services.ratelimit import RateLimitUnavailable, ensure_not_blocked, record_rejection
from app.services.twin import TwinError, build_twin, twin_id

logger = logging.getLogger(__name__)

VPN_DEVICE_TYPES = ("rover", "gateway")  # sensors use MQTT over mTLS, no VPN key


@dataclass(frozen=True)
class ClaimResult:
    device: Device
    preauth: PreAuthKey | None


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


def _limiter_down(tenant_id: str) -> HTTPException:
    logger.error("claim rate limiter unavailable — refusing claims", extra={"tenant_id": tenant_id})
    return _http(status.HTTP_503_SERVICE_UNAVAILABLE, "Claims are temporarily unavailable")


async def _ensure_not_blocked(svc: Services, *, tenant_id: str, device_uuid: str) -> None:
    try:
        await ensure_not_blocked(svc.limiter, device_uuid=device_uuid, tenant_id=tenant_id, settings=svc.settings)
    except RateLimitUnavailable:
        raise _limiter_down(tenant_id) from None


async def _reject(svc: Services, *, tenant_id: str, device_uuid: str, actor: str, ip: str | None) -> HTTPException:
    async with svc.db.tenant_tx(tenant_id) as conn:
        await DeviceRepo(conn).add_event(device_uuid, tenant_id, "CLAIM_REJECTED", actor, ip, {"reason": "bad_code"})
    try:
        await record_rejection(svc.limiter, device_uuid=device_uuid, tenant_id=tenant_id)
    except RateLimitUnavailable:
        raise _limiter_down(tenant_id) from None
    logger.warning("claim rejected", extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
    return _http(status.HTTP_400_BAD_REQUEST, "Invalid claim code")


async def validate(svc: Services, *, tenant_id: str, device_uuid: str, claim_code: str, actor: str,
                   ip: str | None) -> Device:
    await _ensure_not_blocked(svc, tenant_id=tenant_id, device_uuid=device_uuid)
    async with svc.db.tenant_tx(tenant_id) as conn:
        device = _check_state(await DeviceRepo(conn).get(device_uuid))
    if not _code_ok(svc, device, claim_code):
        raise await _reject(svc, tenant_id=tenant_id, device_uuid=device_uuid, actor=actor, ip=ip)
    return device


async def claim(svc: Services, *, tenant_id: str, device_uuid: str, claim_code: str, display_name: str | None,
                actor: str, ip: str | None) -> ClaimResult:
    await _ensure_not_blocked(svc, tenant_id=tenant_id, device_uuid=device_uuid)
    hs_user = headscale_user_for(tenant_id)
    preauth: PreAuthKey | None = None
    created_twin: str | None = None
    rejected = False
    try:
        async with svc.db.tenant_tx(tenant_id) as conn:
            repo = DeviceRepo(conn)
            device = _check_state(await repo.get_for_update(device_uuid))
            if not _code_ok(svc, device, claim_code):
                rejected = True
            else:
                entity_type, entity_id = twin_id(device.device_type, tenant_id, device_uuid)
                needs_vpn = device.device_type in VPN_DEVICE_TYPES
                writer = svc.twin_writer(tenant_id)
                try:
                    if needs_vpn:
                        await svc.headscale.ensure_user(hs_user)
                    await writer.upsert(
                        build_twin(device.device_type, tenant_id, device_uuid, display_name or device.display_name))
                    created_twin = entity_id
                    if needs_vpn:
                        preauth = await svc.headscale.create_preauth_key(hs_user, svc.settings.preauth_ttl_minutes)
                finally:
                    await writer.close()
                claimed = await repo.mark_claimed(
                    device_uuid, claimed_by=actor, headscale_user=hs_user if needs_vpn else None,
                    preauth_key_id=preauth.id if preauth else None,
                    preauth_expires=preauth.expires_at if preauth else None,
                    ngsi_entity_id=entity_id, ngsi_entity_type=entity_type, display_name=display_name,
                )
                await repo.add_event(device_uuid, tenant_id, "CLAIMED", actor, ip,
                                     {"preauth_key_id": preauth.id if preauth else None, "ngsi_entity_id": entity_id})
    except HTTPException:
        raise
    except (HeadscaleError, TwinError) as exc:
        await _undo(svc, tenant_id, hs_user, preauth, created_twin, device_uuid)
        logger.error("claim failed: %s", exc, extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
        raise _http(status.HTTP_502_BAD_GATEWAY, "Device network provisioning failed, retry later") from None
    except Exception as exc:  # DB failure after remote effects: undo them, report
        await _undo(svc, tenant_id, hs_user, preauth, created_twin, device_uuid)
        logger.error("claim failed: %s", type(exc).__name__, extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
        raise _http(status.HTTP_502_BAD_GATEWAY, "Device activation failed, retry later") from None
    if rejected:
        raise await _reject(svc, tenant_id=tenant_id, device_uuid=device_uuid, actor=actor, ip=ip)
    logger.info("device claimed", extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
    return ClaimResult(device=claimed, preauth=preauth)


async def _undo(svc: Services, tenant_id: str, hs_user: str, preauth: PreAuthKey | None, twin: str | None,
                device_uuid: str) -> None:
    """Best effort: remove what a failed claim created, so nothing claims a PENDING device is live."""
    if preauth is not None:
        try:
            await svc.headscale.expire_preauth_key(hs_user, preauth.key)
        except HeadscaleError as exc:
            logger.error("could not expire orphan pre-auth key %s: %s", preauth.id, exc,
                         extra={"device_uuid": device_uuid})
    if twin is not None:
        writer = svc.twin_writer(tenant_id)
        try:
            await writer.delete(twin)
        except TwinError as exc:
            logger.error("could not remove twin of failed claim: %s", exc, extra={"device_uuid": device_uuid})
        finally:
            await writer.close()


def _match_node(device: Device, nodes: list[Node]) -> Node | None:
    return (next((n for n in nodes if device.node_id and n.id == device.node_id), None)
            or next((n for n in nodes if device.preauth_key_id and n.preauth_key_id == device.preauth_key_id), None)
            or next((n for n in nodes if device.device_uuid in (n.given_name, n.hostname)), None))


@dataclass(frozen=True)
class NetworkView:
    device: Device
    node: Node | None
    unknown: bool  # True when Headscale could not be asked: "no node" would be a guess


async def reconcile_node(svc: Services, device: Device, nodes: list[Node] | None = None) -> NetworkView:
    """Find the device's tailnet node; persist it the first time it is seen.

    Headscale being unreachable degrades to an unknown network state (the registry stays readable).
    """
    if device.state != "CLAIMED" or not device.headscale_user:
        return NetworkView(device, None, False)
    try:
        if nodes is None:
            nodes = await svc.headscale.list_nodes(device.headscale_user)
    except HeadscaleError as exc:
        logger.warning("node lookup failed: %s", exc, extra={"device_uuid": device.device_uuid})
        return NetworkView(device, None, True)
    node = _match_node(device, nodes)
    if node and node.id != device.node_id:
        async with svc.db.tenant_tx(device.tenant_id) as conn:
            repo = DeviceRepo(conn)
            device = await repo.set_node(device.device_uuid, node_id=node.id, node_hostname=node.given_name or
                                         node.hostname, node_ip=node.ip)
            await repo.add_event(device.device_uuid, device.tenant_id, "NODE_SEEN", "system", None,
                                 {"node_id": node.id})
    return NetworkView(device, node, False)


async def reissue_key(svc: Services, *, tenant_id: str, device_uuid: str, actor: str, ip: str | None) -> PreAuthKey:
    """New single-use key for a claimed robot/gateway that never joined (old key lapsed or lost).

    Refused once a node exists — the device is on the network and needs no key.
    The previous key is expired if still unused. Headscale unreachable: nothing changes.
    """
    preauth: PreAuthKey | None = None
    try:
        async with svc.db.tenant_tx(tenant_id) as conn:
            repo = DeviceRepo(conn)
            device = await repo.get_for_update(device_uuid)
            if device is None:
                raise _http(status.HTTP_404_NOT_FOUND, "Device not found")
            if device.state != "CLAIMED" or device.device_type not in VPN_DEVICE_TYPES or not device.headscale_user:
                raise _http(status.HTTP_409_CONFLICT, "Only an active robot or gateway can get a new key")
            if _match_node(device, await svc.headscale.list_nodes(device.headscale_user)) is not None:
                raise _http(status.HTTP_409_CONFLICT, "The device has already joined the network")
            expired_old = bool(device.preauth_key_id) and await svc.headscale.expire_unused_key(
                device.headscale_user, device.preauth_key_id)
            preauth = await svc.headscale.create_preauth_key(device.headscale_user, svc.settings.preauth_ttl_minutes)
            await repo.set_preauth(device_uuid, preauth_key_id=preauth.id, preauth_expires=preauth.expires_at)
            await repo.add_event(device_uuid, tenant_id, "KEY_REISSUED", actor, ip,
                                 {"preauth_key_id": preauth.id, "previous_expired": expired_old})
    except HTTPException:
        raise
    except HeadscaleError as exc:
        await _undo(svc, tenant_id, headscale_user_for(tenant_id), preauth, None, device_uuid)
        logger.error("key reissue failed: %s", exc, extra={"device_uuid": device_uuid})
        raise _http(status.HTTP_502_BAD_GATEWAY, "Device network provisioning failed, retry later") from None
    except Exception as exc:
        await _undo(svc, tenant_id, headscale_user_for(tenant_id), preauth, None, device_uuid)
        logger.error("key reissue failed: %s", type(exc).__name__, extra={"device_uuid": device_uuid})
        raise _http(status.HTTP_502_BAD_GATEWAY, "Key reissue failed, retry later") from None
    logger.info("device key reissued", extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
    return preauth


async def revoke(svc: Services, *, tenant_id: str, device_uuid: str, actor: str, ip: str | None) -> None:
    details: dict[str, str] = {}
    async with svc.db.tenant_tx(tenant_id) as conn:
        repo = DeviceRepo(conn)
        device = await repo.get_for_update(device_uuid)
        if device is None:
            raise _http(status.HTTP_404_NOT_FOUND, "Device not found")
        if device.state == "REVOKED":
            raise _http(status.HTTP_409_CONFLICT, "Device already revoked")

        if device.state == "CLAIMED" and device.headscale_user:
            # Network access first, from a fresh listing: if Headscale cannot
            # answer, nothing changes; a stored node id that no longer exists is ignored.
            try:
                node = _match_node(device, await svc.headscale.list_nodes(device.headscale_user))
                if node is not None:
                    await svc.headscale.delete_node(node.id)
                    details["node_id"] = node.id
                if device.preauth_key_id and await svc.headscale.expire_unused_key(
                        device.headscale_user, device.preauth_key_id):
                    details["preauth_key"] = "expired"
            except HeadscaleError as exc:
                logger.error("revocation could not reach Headscale: %s", exc, extra={"device_uuid": device_uuid})
                raise _http(status.HTTP_502_BAD_GATEWAY, "Could not remove the device from the network") from None

        if device.state == "CLAIMED" and device.ngsi_entity_id:
            writer = svc.twin_writer(tenant_id)
            try:
                await writer.mark_revoked(device.ngsi_entity_id)
                details["twin"] = "revoked"
            except TwinError as exc:  # the twin is metadata; revocation must not depend on it
                logger.error("twin revoke failed: %s", exc, extra={"device_uuid": device_uuid})
                details["twin"] = "sync_failed"
            finally:
                await writer.close()

        try:
            await repo.mark_revoked(device_uuid, revoked_by=actor)
        except InvalidTransition:
            raise _http(status.HTTP_409_CONFLICT, "Device already revoked") from None
        await repo.add_event(device_uuid, tenant_id, "REVOKED", actor, ip, details or None)
    logger.info("device revoked", extra={"device_uuid": device_uuid, "tenant_id": tenant_id})
