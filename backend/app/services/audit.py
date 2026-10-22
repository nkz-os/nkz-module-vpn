"""Write audit log entries for device lifecycle events. Best-effort."""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import DeviceAuditLog

logger = logging.getLogger(__name__)


async def log_event(
    db: AsyncSession,
    *,
    tenant_id: str,
    device_uuid: str,
    action: str,
    actor_sub: str,
    ip_address: str | None = None,
) -> None:
    try:
        entry = DeviceAuditLog(
            tenant_id=tenant_id,
            device_uuid=device_uuid,
            action=action,
            actor_sub=actor_sub,
            ip_address=ip_address,
        )
        db.add(entry)
    except Exception as e:
        logger.error("Failed to write audit log: %s", e)
