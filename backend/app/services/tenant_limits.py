"""
Query admin_platform.tenant_limits for device quota enforcement.
The billing module manages tenant_limits. This service is read-only.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

DEFAULT_MAX_DEVICES = 50


async def get_max_devices(db: AsyncSession, tenant_id: str) -> int:
    try:
        result = await db.execute(
            text(
                "SELECT max_devices FROM admin_platform.tenant_limits "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        row = result.fetchone()
        if row and row[0] is not None:
            return row[0]
    except Exception as e:
        logger.warning(
            "Could not read tenant_limits for %s: %s — using default %d",
            tenant_id, e, DEFAULT_MAX_DEVICES,
        )
    return DEFAULT_MAX_DEVICES


async def count_active_devices(db: AsyncSession, tenant_id: str) -> int:
    from app.models import ProvisionedDevice

    result = await db.execute(
        select(func.count(ProvisionedDevice.uuid)).where(
            ProvisionedDevice.tenant_id == tenant_id,
            ProvisionedDevice.state.in_(["PENDING", "CONSUMED"]),
        )
    )
    return result.scalar() or 0
