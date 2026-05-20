"""
Auth dependency wrapper.
Delegates to API Gateway injected headers (X-Tenant-ID, X-User-ID, X-User-Roles).
"""

import logging
from fastapi import Request, HTTPException, status, Depends
# from nkz_platform_sdk import require_auth  # Assuming SDK exports this

logger = logging.getLogger(__name__)

def require_auth(request: Request) -> dict:
    """Dependency: Lee las cabeceras inyectadas por el api-gateway."""
    user_id = request.headers.get("X-User-ID")
    roles = request.headers.get("X-User-Roles", "").split(",")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-ID header from API Gateway"
        )
    return {
        "sub": user_id,
        "realm_access": {"roles": [r.strip() for r in roles if r.strip()]}
    }


def get_tenant_id(request: Request) -> str:
    """Dependency: Extrae el tenant ID del header."""
    tenant_id = request.headers.get("X-Tenant-ID") or request.headers.get("Fiware-Service")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID header is required (X-Tenant-ID or Fiware-Service)"
        )
    return tenant_id


async def require_factory_role(payload: dict = Depends(require_auth)) -> dict:
    """Dependency: requiere rol 'Factory' o 'PlatformAdmin'."""
    roles = payload.get("realm_access", {}).get("roles", [])
    if "Factory" not in roles and "PlatformAdmin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Factory or PlatformAdmin role required",
        )
    return payload
