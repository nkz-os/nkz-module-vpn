"""
Middleware that extracts tenant_id from request headers and stores it
on request.state for use by the DB session (RLS) and downstream services.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from app.common.tenant_utils import normalize_tenant_id

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Extract and normalize tenant_id from Fiware-Service or X-Tenant-ID header."""

    async def dispatch(self, request, call_next):
        raw = request.headers.get("Fiware-Service") or request.headers.get("X-Tenant-ID")
        if raw:
            try:
                request.state.tenant_id = normalize_tenant_id(raw)
            except ValueError:
                logger.warning("Invalid tenant ID in header: %s", raw)
        response = await call_next(request)
        return response
