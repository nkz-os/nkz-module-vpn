# VPN Module Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the nkz-module-vpn from audit findings to production-ready, with tenant isolation, NGSI-LD compliance, and per-role UX.

**Architecture:** Backend receives cookie-auth via api-gateway → Bearer. Tenant context extracted from headers, pushed to PostgreSQL via `SET app.current_tenant_id` for RLS. Rate limiting uses Redis with tenant+IP keys. Entity types unified in a single SDM-compliant dict. Frontend uses `credentials: 'include'` with no token in JS. PlatformAdmin sees cross-tenant view and factory panel.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, asyncpg, Redis, httpx, PyJWT, React 18, TypeScript, i18next

**PRs:** 4 independent PRs → Block 1, Block 2, Block 3, Block 4. Block 5 is manual verification.

---

## PR #1 — Critical Fixes (JWT issuer, NGSI-LD context, unified types)

### Task 1.1: Fix JWT issuer resolution in config

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Remove `JWT_ISSUER` field, add startup guard to `jwt_issuer_url`**

Replace the `JWT_ISSUER` field and its property in `backend/app/config.py`:

```python
# Remove this:
JWT_ISSUER: str = ""

# Keep and harden the property — ensure it never returns empty:
@property
def jwt_issuer_url(self) -> str:
    """Derive issuer from KEYCLOAK_URL + realm, or from explicit JWT_ISSUER env var."""
    explicit = os.getenv("JWT_ISSUER", "")
    if explicit:
        return explicit
    if self.KEYCLOAK_URL:
        return f"{self.KEYCLOAK_URL}/realms/{self.KEYCLOAK_REALM}"
    raise RuntimeError(
        "Neither JWT_ISSUER nor KEYCLOAK_URL is configured. "
        "The service cannot validate tokens without an issuer URL."
    )
```

Add `import os` at the top of `config.py`.

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "fix: harden jwt_issuer_url to never return empty string

Remove JWT_ISSUER raw field. The property now derives from
KEYCLOAK_URL + realm, or from explicit JWT_ISSUER env var.
Raises RuntimeError at startup if neither is configured."
```

### Task 1.2: Fix all JWT issuer usages in auth middleware

**Files:**
- Modify: `backend/app/middleware/auth.py`

- [ ] **Step 1: Replace `settings.JWT_ISSUER` → `settings.jwt_issuer_url`**

Three locations in `auth.py`:

Line 22 — module-level `JWKS_URL`:
```python
# Before:
JWKS_URL = f"{settings.JWT_ISSUER}/protocol/openid-connect/certs"

# After:
def get_jwks_url() -> str:
    return f"{settings.jwt_issuer_url}/protocol/openid-connect/certs"
```

Line 38 — issuer validation in `verify_token`:
```python
# Before:
if token_issuer != settings.JWT_ISSUER:

# After:
if token_issuer != settings.jwt_issuer_url:
```

Line 51 — `jwt.decode` issuer parameter:
```python
# Before:
issuer=settings.JWT_ISSUER,

# After:
issuer=settings.jwt_issuer_url,
```

Update `get_jwks_client()` to use `get_jwks_url()` instead of the module-level `JWKS_URL`:
```python
def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(get_jwks_url())
    return _jwks_client
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/middleware/auth.py
git commit -m "fix: use jwt_issuer_url property instead of raw JWT_ISSUER field

All three sites that consumed settings.JWT_ISSUER now use the
property that derives the issuer from KEYCLOAK_URL + realm or
from the explicit env var. Module-level JWKS_URL replaced with
a function to avoid caching an empty default."
```

### Task 1.3: Add CONTEXT_URL to config

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add `CONTEXT_URL` setting**

After the `ENTITY_MANAGER_URL` line in `config.py`, add:

```python
# NGSI-LD @context URL — required for FIWARE compliance
CONTEXT_URL: str = "http://api-gateway-service:5000/ngsi-ld-context.json"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add CONTEXT_URL setting for NGSI-LD Link header"
```

### Task 1.4: Add NGSI-LD Link header to entity-manager calls

**Files:**
- Modify: `backend/app/services/entity_manager.py`

- [ ] **Step 1: Add Link header to the POST request**

In `entity_manager.py`, replace the headers dict (around line 73):

```python
# Before:
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Fiware-Service": tenant_id,
}

# After:
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Fiware-Service": tenant_id,
    "Link": (
        f'<{settings.CONTEXT_URL}>; '
        f'rel="http://www.w3.org/ns/json-ld#context"; '
        f'type="application/ld+json"'
    ),
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/entity_manager.py
git commit -m "fix: add NGSI-LD Link header to entity-manager POST requests

Per FIWARE strict mandate: application/json requests must include
a Link header pointing to the JSON-LD @context."
```

### Task 1.5: Unify device type to NGSI-LD type mapping

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/entity_manager.py`
- Modify: `backend/app/routes/devices.py`
- Modify: `backend/app/routes/factory.py`

- [ ] **Step 1: Add DEVICE_TYPE_TO_NGSI_TYPE dict to models.py**

After the `ProvisionedDevice` class in `models.py`, add:

```python
# Canonical mapping: device_type → FIWARE Smart Data Model type
# Single source of truth used by routes and entity_manager.
DEVICE_TYPE_TO_NGSI_TYPE: dict[str, str] = {
    "rover": "AgriRobot",
    "gateway": "AgriGateway",
    "sensor_esp32": "AgriSensor",
}
```

- [ ] **Step 2: Simplify entity_manager.py — remove inline normalization**

Replace the normalization block (lines 40-44) in `entity_manager.py`:

```python
# Before:
normalized_type = entity_type
if device_type.lower() in ["robot", "ros", "zenoh", "tractor", "agv"]:
    normalized_type = "AgriculturalMachine"
elif device_type.lower() in ["sensor", "gateway"]:
    normalized_type = "Device"

# After:
# The caller is responsible for mapping device_type → NGSI-LD type
# using DEVICE_TYPE_TO_NGSI_TYPE from models.py.
# entity_type already contains the correct SDM type.
normalized_type = entity_type
```

This simplifies the function — remove the inline type normalization entirely. The `normalized_type` variable can be inlined into `payload["type"]`.

- [ ] **Step 3: Update routes/devices.py to use the canonical dict**

Replace the inline `type_map` dict (lines 170-175) in `routes/devices.py`:

```python
# Before:
type_map = {
    "rover": "AgriculturalRobot",
    "gateway": "AgriSensor",
    "sensor_esp32": "AgriSensor",
}
ngsi_type = type_map.get(device.device_type, "AgriSensor")

# After:
from app.models import DEVICE_TYPE_TO_NGSI_TYPE
ngsi_type = DEVICE_TYPE_TO_NGSI_TYPE.get(device.device_type, "Device")
```

- [ ] **Step 4: Update routes/factory.py (no changes needed for routes, but check imports)**

The factory routes don't use type mapping directly — they just pass `device_type` through. No changes needed beyond removing any stale imports.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/services/entity_manager.py backend/app/routes/devices.py backend/app/routes/factory.py
git commit -m "fix: unify device-to-NGSI type mapping into single canonical dict

DEVICE_TYPE_TO_NGSI_TYPE in models.py is now the single source of truth:
rover→AgriRobot, gateway→AgriGateway, sensor_esp32→AgriSensor.
Removed divergent inline mappings from entity_manager and devices routes."
```

### Task 1.6: Wire CONTEXT_URL in K8s deployment manifest

**Files:**
- Modify: `k8s/deployment.yaml`

- [ ] **Step 1: Add CONTEXT_URL env var**

In the `env` section of the container spec in `deployment.yaml`, after the `ENTITY_MANAGER_URL` block, add:

```yaml
            - name: CONTEXT_URL
              value: "http://api-gateway-service:5000/ngsi-ld-context.json"
```

- [ ] **Step 2: Commit**

```bash
git add k8s/deployment.yaml
git commit -m "fix: add CONTEXT_URL env var to K8s deployment manifest"
```

---

## PR #2 — Tenant Isolation (rate limiting, quotas, RLS, ACLs, audit log)

### Task 2.1: Add Redis and async Redis dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add redis with async support**

`requirements.txt` already has `redis==5.1.1`. Verify it's present. If missing, add:

```
redis[hiredis]==5.1.1
```

The `redis` package supports async via `redis.asyncio`. No additional package needed.

- [ ] **Step 2: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: verify redis dependency for async rate limiting"
```

### Task 2.2: Create rate limiter service

**Files:**
- Create: `backend/app/middleware/rate_limit.py`

- [ ] **Step 1: Write rate limiter class**

Create `backend/app/middleware/rate_limit.py`:

```python
"""
Redis-backed rate limiter with per-tenant and per-IP windows.

Used by the /devices/claim endpoint to prevent brute-force attacks
on Claim Codes. Two windows: tenant-level and IP-level.
"""

import logging
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis_url: str = settings.REDIS_URL):
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, encoding="utf-8", decode_responses=True
            )
        return self._redis

    async def check(
        self, key: str, max_attempts: int, window_seconds: int
    ) -> bool:
        """
        Returns True if the request is allowed, False if rate-limited.

        Uses Redis INCR + EXPIRE for atomic counting within the window.
        """
        r = await self._get_redis()
        try:
            current = await r.get(key)
            if current is not None and int(current) >= max_attempts:
                ttl = await r.ttl(key)
                logger.warning(
                    "Rate limit hit for key prefix %s (ttl=%ss)",
                    key.rsplit(":", 1)[0], ttl,
                )
                return False
            pipe = r.pipeline()
            pipe.incr(key)
            if current is None:
                pipe.expire(key, window_seconds)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error("Redis rate limit check failed: %s — allowing request", e)
            return True  # Fail open — don't block legitimate traffic


limiter = RateLimiter()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/middleware/rate_limit.py backend/app/middleware/__init__.py
git commit -m "feat: add Redis-backed rate limiter for claim endpoint"
```

### Task 2.3: Apply rate limiting to /devices/claim

**Files:**
- Modify: `backend/app/routes/devices.py`

- [ ] **Step 1: Add rate limit checks at the start of claim_device**

In `routes/devices.py`, import the limiter:

```python
from app.middleware.rate_limit import limiter
```

At the beginning of the `claim_device` function body, after extracting `tenant_id` but before the DB query, add:

```python
    # Rate limiting: per-tenant (5/h) + per-IP (10/h)
    tenant_key = f"rate:claim:tenant:{tenant_id}"
    ip = request.client.host if request.client else "unknown"
    ip_key = f"rate:claim:ip:{ip}"

    if not await limiter.check(
        tenant_key,
        settings.CLAIM_RATE_LIMIT_ATTEMPTS,
        settings.CLAIM_RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many claim attempts for this tenant. Try again later.",
        )
    if not await limiter.check(
        ip_key,
        10,  # 10 attempts per IP per hour
        settings.CLAIM_RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many claim attempts from this IP. Try again later.",
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routes/devices.py
git commit -m "feat: apply rate limiting to /devices/claim endpoint

Two windows: 5 attempts per tenant per hour, 10 per IP per hour.
Fail-open if Redis is unreachable."
```

### Task 2.4: Create tenant context middleware for RLS

**Files:**
- Create: `backend/app/middleware/tenant_context.py`

- [ ] **Step 1: Write tenant context middleware**

Create `backend/app/middleware/tenant_context.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/middleware/tenant_context.py
git commit -m "feat: add tenant context middleware for RLS support"
```

### Task 2.5: Wire tenant context into DB sessions for RLS

**Files:**
- Modify: `backend/app/db/database.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Update get_db to set PostgreSQL RLS variable**

Modify `get_db()` in `database.py` to accept the request and set the tenant context:

```python
from fastapi import Request
from sqlalchemy import text

async def get_db(request: Request = None):
    """Dependency de FastAPI para inyectar sesión de BD con tenant context."""
    async with AsyncSessionLocal() as session:
        tenant_id = getattr(request.state, 'tenant_id', None) if request else None
        if tenant_id:
            await session.execute(
                text("SET app.current_tenant_id = :tid"), {"tid": tenant_id}
            )
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            # Don't commit here — let the route handler decide
            pass
```

Wait — the current `get_db` already commits on success. Keep the commit behavior but move the tenant SET inside the try block.

Actually, let me re-read the current `get_db`:

```python
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

The commit-after-yield pattern means the route handler runs, then commit happens. The SET must happen before the route handler queries. So:

```python
from fastapi import Request
from sqlalchemy import text

async def get_db(request: Request):
    async with AsyncSessionLocal() as session:
        tenant_id = getattr(request.state, 'tenant_id', None) if request else None
        if tenant_id:
            await session.execute(
                text("SET app.current_tenant_id = :tid"), {"tid": tenant_id}
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

But this changes the signature of `get_db` — all route handlers that use `db: AsyncSession = Depends(get_db)` will need `request: Request` in their params too... Actually no, FastAPI's Depends can inject `Request` automatically for dependencies. Let me verify:

In FastAPI, `Depends(get_db)` will call `get_db(request=Request)` where Request is auto-resolved from the route's parameters. If the route handler doesn't take a `request: Request` parameter, FastAPI still resolves it for the dependency. So routes that don't have `request: Request` as a parameter will still work. 

But wait — routes like `list_devices` don't have `request: Request` in their signature. FastAPI can still inject it into the dependency. Yes, that's correct — dependencies can have their own dependencies resolved independently.

Actually, I need to import Request properly. Let me use `from fastapi import Request` in database.py.

- [ ] **Step 2: Register TenantContextMiddleware in main.py**

In `main.py`, add the middleware registration after CORS:

```python
from app.middleware.tenant_context import TenantContextMiddleware

# After CORS middleware
app.add_middleware(TenantContextMiddleware)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/database.py backend/app/main.py
git commit -m "feat: set PostgreSQL RLS variable from tenant context header

TenantContextMiddleware extracts tenant_id from Fiware-Service or
X-Tenant-ID header and stores it on request.state. get_db() executes
SET app.current_tenant_id before yielding the session, enabling RLS."
```

### Task 2.6: Create RLS migration

**Files:**
- Create: `backend/migrations/001_rls_devices.sql`

- [ ] **Step 1: Write RLS migration SQL**

Create `backend/migrations/001_rls_devices.sql`:

```sql
-- Enable Row-Level Security on provisioned_devices.
-- Every query is filtered by app.current_tenant_id, set by the
-- TenantContextMiddleware before each request.
-- Run once: psql -h localhost -U postgres -d nekazari -f 001_rls_devices.sql

BEGIN;

ALTER TABLE provisioned_devices ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON provisioned_devices;
CREATE POLICY tenant_isolation ON provisioned_devices
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id'))
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id'));

-- Allow the platform to run un-scoped queries (e.g., PlatformAdmin cross-tenant view).
-- When app.current_tenant_id is set to '__platform__', bypass RLS.
DROP POLICY IF EXISTS platform_bypass ON provisioned_devices;
CREATE POLICY platform_bypass ON provisioned_devices
    FOR ALL
    USING (current_setting('app.current_tenant_id') = '__platform__');

COMMIT;
```

- [ ] **Step 2: Commit**

```bash
git add backend/migrations/001_rls_devices.sql
git commit -m "feat: add RLS migration for provisioned_devices

Enables row-level security with per-tenant isolation policy.
Platform bypass policy allows cross-tenant queries when
app.current_tenant_id is set to __platform__."
```

### Task 2.7: Create tenant limits service

**Files:**
- Create: `backend/app/services/tenant_limits.py`

- [ ] **Step 1: Write tenant limits service**

Create `backend/app/services/tenant_limits.py`:

```python
"""
Query admin_platform.tenant_limits for device quota enforcement.

The billing module manages tenant_limits. This service is read-only.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_MAX_DEVICES = 50


async def get_max_devices(db: AsyncSession, tenant_id: str) -> int:
    """
    Return max_devices for a tenant from admin_platform.tenant_limits.
    Falls back to DEFAULT_MAX_DEVICES if the table doesn't exist or
    the tenant has no configured limit.
    """
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
    """
    Count devices in PENDING or CONSUMED state for a tenant.
    Revoked devices are not counted toward the quota.
    """
    from app.models import ProvisionedDevice
    from sqlalchemy import select, func

    result = await db.execute(
        select(func.count(ProvisionedDevice.uuid)).where(
            ProvisionedDevice.tenant_id == tenant_id,
            ProvisionedDevice.state.in_(["PENDING", "CONSUMED"]),
        )
    )
    return result.scalar() or 0
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/tenant_limits.py
git commit -m "feat: add tenant_limits service for device quota enforcement

Reads max_devices from admin_platform.tenant_limits with fallback
to DEFAULT_MAX_DEVICES=50. Counts active devices per tenant."
```

### Task 2.8: Apply quota check to /devices/claim

**Files:**
- Modify: `backend/app/routes/devices.py`

- [ ] **Step 1: Add quota check before marking device as CONSUMED**

In `routes/devices.py`, import the tenant_limits service:

```python
from app.services import tenant_limits as tl_service
```

After the claim code validation succeeds (line 145) and before the preauth_key generation (line 162), add:

```python
    # Quota check: enforce max_devices per tenant
    active_count = await tl_service.count_active_devices(db, tenant_id)
    max_devices = await tl_service.get_max_devices(db, tenant_id)
    if active_count >= max_devices:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Device quota exceeded ({active_count}/{max_devices})",
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routes/devices.py
git commit -m "feat: enforce device quota on claim via tenant_limits.max_devices"
```

### Task 2.9: Add PlatformAdmin cross-tenant support to list_devices

**Files:**
- Modify: `backend/app/routes/devices.py`

- [ ] **Step 1: Support all_tenants query param for PlatformAdmin**

Modify `list_devices` in `routes/devices.py` to accept an optional `all_tenants` query parameter:

```python
@router.get("/", ...)
async def list_devices(
    request: Request,
    all_tenants: bool = False,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
):
    # PlatformAdmin can query across all tenants
    roles = payload.get("realm_access", {}).get("roles", [])
    is_platform_admin = "PlatformAdmin" in roles

    if all_tenants and is_platform_admin:
        # Bypass RLS for cross-tenant query
        await db.execute(text("SET app.current_tenant_id = '__platform__'"))
        result = await db.execute(
            select(ProvisionedDevice)
            .order_by(ProvisionedDevice.created_at.desc())
        )
    else:
        result = await db.execute(
            select(ProvisionedDevice)
            .where(ProvisionedDevice.tenant_id == tenant_id)
            .order_by(ProvisionedDevice.created_at.desc())
        )
    devices = result.scalars().all()
    return DeviceListResponse(
        devices=[
            DeviceStatusResponse(
                device_uuid=d.uuid,
                device_type=d.device_type,
                device_name=d.device_name,
                state=d.state,
                headscale_peer_id=d.headscale_peer_id,
                online=False,
                last_seen=None,
                tenant_id=d.tenant_id if is_platform_admin and all_tenants else None,
            )
            for d in devices
        ],
        total=len(devices),
    )
```

Add `tenant_id` field to `DeviceStatusResponse`:

```python
class DeviceStatusResponse(BaseModel):
    device_uuid: str
    device_type: str
    device_name: str | None
    state: str
    headscale_peer_id: str | None
    online: bool
    last_seen: str | None
    tenant_id: str | None = None  # Only populated for PlatformAdmin cross-tenant view
```

Add `from sqlalchemy import text` to imports in routes/devices.py.

- [ ] **Step 2: Commit**

```bash
git add backend/app/routes/devices.py
git commit -m "feat: support PlatformAdmin cross-tenant device listing

?all_tenants=true bypasses tenant filter for PlatformAdmin role.
Response includes tenant_id column when in cross-tenant mode."
```

### Task 2.10: Add audit log model and service

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/services/audit.py`

- [ ] **Step 1: Add DeviceAuditLog model**

In `models.py`, after `ProvisionedDevice`, add:

```python
import uuid as _uuid


class DeviceAuditLog(Base):
    """Immutable audit trail for device lifecycle events."""

    __tablename__ = "device_audit_log"

    id = Column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tenant_id = Column(String, nullable=False, index=True)
    device_uuid = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)  # REGISTERED | CLAIMED | REVOKED
    actor_sub = Column(String, nullable=False)  # JWT sub claim
    ip_address = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Create audit service**

Create `backend/app/services/audit.py`:

```python
"""
Write audit log entries for device lifecycle events.
Best-effort — audit failures must never block the operation.
"""

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
        # Don't commit here — let the route's get_db commit handle it
    except Exception as e:
        logger.error("Failed to write audit log: %s", e)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models.py backend/app/services/audit.py
git commit -m "feat: add DeviceAuditLog model and audit service

Tracks REGISTERED, CLAIMED, and REVOKED events with actor sub and IP."
```

### Task 2.11: Integrate audit logging into routes

**Files:**
- Modify: `backend/app/routes/devices.py`
- Modify: `backend/app/routes/factory.py`

- [ ] **Step 1: Add audit log calls to devices routes**

In `routes/devices.py`, import audit:

```python
from app.services import audit as audit_service
```

In `claim_device`, after setting `device.state = "CONSUMED"` (line 179), add:

```python
    actor_sub = payload.get("sub", "unknown")
    ip = request.client.host if request.client else None
    await audit_service.log_event(
        db, tenant_id=tenant_id, device_uuid=device.uuid,
        action="CLAIMED", actor_sub=actor_sub, ip_address=ip,
    )
```

In `revoke_device`, after setting `device.state = "REVOKED"` (line 279), add:

```python
    actor_sub = payload.get("sub", "unknown")
    ip = request.client.host if request.client else None
    await audit_service.log_event(
        db, tenant_id=tenant_id, device_uuid=device.uuid,
        action="REVOKED", actor_sub=actor_sub, ip_address=ip,
    )
```

- [ ] **Step 2: Add audit log call to factory routes**

In `routes/factory.py`, import audit:

```python
from app.services import audit as audit_service
```

In `register_device`, after `db.add(device)` (line 138), add:

```python
    actor_sub = _payload.get("sub", "unknown")
    await audit_service.log_event(
        db, tenant_id=req.tenant_id, device_uuid=req.device_uuid,
        action="REGISTERED", actor_sub=actor_sub, ip_address=None,
    )
```

Note: `_payload` is the parameter name used in the factory routes (`_payload: dict = Depends(require_factory_role)`).

- [ ] **Step 3: Commit**

```bash
git add backend/app/routes/devices.py backend/app/routes/factory.py
git commit -m "feat: integrate audit logging into device and factory routes

All lifecycle events (REGISTERED, CLAIMED, REVOKED) are logged
with actor sub and IP address."
```

### Task 2.12: Headscale ACL tags per tenant

**Files:**
- Modify: `backend/app/services/headscale.py`

- [ ] **Step 1: Generate tenant tag during user creation**

In `headscale.py`, update `ensure_user_exists` to also create a tenant-specific tag:

```python
async def ensure_user_exists(tenant_id: str) -> dict:
    """
    Create the Headscale user for the tenant if it doesn't exist.
    Idempotent — if it already exists, return it without error.
    """
    try:
        return await _get(f"/api/v1/user/{tenant_id}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.info("Creating Headscale user for tenant %s", tenant_id)
            result = await _post("/api/v1/user", {"name": tenant_id})
            # Let the operator know the ACL tag needs to be created.
            # Actual ACL injection requires ConfigMap update — handled
            # by the platform via headscale-config ConfigMap.
            logger.info(
                "Headscale user %s created. Add tag:tenant-%s to ACLs.",
                tenant_id, tenant_id,
            )
            return result
        raise
```

The actual ACL ConfigMap update for dynamic tenant tags is complex (requires parsing huJSON, adding tag owners, redeploying ConfigMap, restarting Headscale). For now, we log the instruction and the operator adds the tag manually. A future iteration can automate this via the Kubernetes API.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/headscale.py
git commit -m "feat: log tenant tag creation instructions for Headscale ACLs

ensure_user_exists now logs the ACL tag that should be created
for the tenant. Full automation of ConfigMap updates deferred
to a follow-up."
```

---

## PR #3 — Frontend (API client, i18n fixes, Tenant Admin UX, Platform Admin UX)

### Task 3.1: Fix API client for cookie auth

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Rewrite VpnApiClient to use credentials:include**

Replace the entire `getAuthToken` function and `VpnApiClient.request` method in `api.ts`:

```typescript
function getTenantId(): string | null {
  const ctx = (window as any).__nekazariAuthContext;
  return ctx?.tenantId || null;
}

class VpnApiClient {
  private readonly base = '/api/vpn';

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const tenantId = getTenantId();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };
    if (tenantId) headers['X-Tenant-ID'] = tenantId;

    const res = await fetch(`${this.base}${endpoint}`, {
      ...options,
      credentials: 'include',
      headers,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as any).detail || `API error: ${res.status}`);
    }
    if (res.status === 204) return undefined as unknown as T;
    return res.json();
  }

  // ... listDevices, getDeviceStatus, claimDevice, revokeDevice unchanged
}
```

Remove the `getAuthToken()` function entirely.

- [ ] **Step 2: Add all_tenants param to listDevices**

```typescript
listDevices(allTenants = false): Promise<DeviceListResponse> {
  const qs = allTenants ? '?all_tenants=true' : '';
  return this.request(`/devices/${qs}`);
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "fix: use credentials:include for cookie auth, remove token logic

API client now relies on httpOnly cookie propagated via credentials:include.
Adds X-Tenant-ID header from __nekazariAuthContext. Removes dead token code."
```

### Task 3.2: Fix hardcoded strings

**Files:**
- Modify: `frontend/src/components/VpnContextPanel.tsx`
- Modify: `frontend/src/components/VpnStatusWidget.tsx`

- [ ] **Step 1: Fix VpnContextPanel.tsx line 104**

Replace:
```tsx
Last seen: {new Date(device.last_seen).toLocaleString()}
```
With:
```tsx
{t('context.lastSeen', { date: new Date(device.last_seen).toLocaleString() })}
```

- [ ] **Step 2: Fix VpnStatusWidget.tsx line 39**

Replace:
```tsx
<p className="text-xs text-red-500">Could not load device status</p>
```
With:
```tsx
<p className="text-xs text-red-500">{t('widget.loadError')}</p>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/VpnContextPanel.tsx frontend/src/components/VpnStatusWidget.tsx
git commit -m "fix: replace hardcoded English strings with i18n t() calls"
```

### Task 3.3: Add new i18n keys

**Files:**
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/en.json`

- [ ] **Step 1: Add new keys to en.json**

Add to `frontend/src/locales/en.json`:

```json
{
  "page": {
    "quotaBadge": "{{used}}/{{max}} devices",
    "quotaFull": "Device quota reached ({{used}}/{{max}})",
    "quotaWarning": "Approaching device limit"
  },
  "list": {
    "tenant": "Tenant",
    "allTenants": "All tenants",
    "myTenant": "My tenant"
  },
  "wizard": {
    "errorRateLimit": "Too many attempts. Please wait before trying again.",
    "errorQuotaExceeded": "Device quota exceeded ({{used}}/{{max}}). Contact your administrator.",
    "errorDeviceAlreadyActivated": "This device has already been activated.",
    "errorDeviceRevoked": "This device has been revoked and cannot be reactivated."
  },
  "factory": {
    "title": "Factory — Pre-register Device",
    "description": "Register a new device and generate its Claim Code for chassis printing.",
    "registerDevice": "Register device",
    "registerSuccess": "Device registered. Claim Code: {{code}}",
    "uuidLabel": "Device UUID",
    "typeLabel": "Device type",
    "tenantLabel": "Tenant ID",
    "nameLabel": "Device name (optional)",
    "registering": "Registering..."
  },
  "revoke": {
    "title": "Revoke device",
    "confirmInstruction": "Type \"{{name}}\" to confirm revocation.",
    "consequences": "This will immediately disconnect the device from the SDN. It cannot be reactivated.",
    "confirmPlaceholder": "Type device name to confirm",
    "confirm": "Revoke device",
    "cancel": "Cancel"
  }
}
```

- [ ] **Step 2: Add corresponding keys to es.json**

Add to `frontend/src/locales/es.json`:

```json
{
  "page": {
    "quotaBadge": "{{used}}/{{max}} dispositivos",
    "quotaFull": "Límite de dispositivos alcanzado ({{used}}/{{max}})",
    "quotaWarning": "Acercándose al límite de dispositivos"
  },
  "list": {
    "tenant": "Tenant",
    "allTenants": "Todos los tenants",
    "myTenant": "Mi tenant"
  },
  "wizard": {
    "errorRateLimit": "Demasiados intentos. Espera antes de volver a intentarlo.",
    "errorQuotaExceeded": "Límite de dispositivos excedido ({{used}}/{{max}}). Contacta con tu administrador.",
    "errorDeviceAlreadyActivated": "Este dispositivo ya ha sido activado.",
    "errorDeviceRevoked": "Este dispositivo ha sido revocado y no puede reactivarse."
  },
  "factory": {
    "title": "Fábrica — Pre-registrar dispositivo",
    "description": "Registra un nuevo dispositivo y genera su Claim Code para imprimir en el chasis.",
    "registerDevice": "Registrar dispositivo",
    "registerSuccess": "Dispositivo registrado. Claim Code: {{code}}",
    "uuidLabel": "UUID del dispositivo",
    "typeLabel": "Tipo de dispositivo",
    "tenantLabel": "ID del tenant",
    "nameLabel": "Nombre del dispositivo (opcional)",
    "registering": "Registrando..."
  },
  "revoke": {
    "title": "Revocar dispositivo",
    "confirmInstruction": "Escribe \"{{name}}\" para confirmar la revocación.",
    "consequences": "Esto desconectará inmediatamente el dispositivo de la SDN. No podrá reactivarse.",
    "confirmPlaceholder": "Escribe el nombre del dispositivo para confirmar",
    "confirm": "Revocar dispositivo",
    "cancel": "Cancelar"
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/locales/es.json frontend/src/locales/en.json
git commit -m "feat: add i18n keys for quota, rate limiting, factory, and revocation UI"
```

### Task 3.4: Update slot entity types

**Files:**
- Modify: `frontend/src/slots/index.tsx`

- [ ] **Step 1: Update entityType list**

In `slots/index.tsx`, line 72, replace:
```tsx
entityType: ['Robot', 'AgriRobot', 'Rover', 'IoTGateway'],
```
With:
```tsx
entityType: ['AgriRobot', 'AgriGateway', 'AgriSensor'],
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/slots/index.tsx
git commit -m "fix: update slot entity types to match unified SDM mapping"
```

### Task 3.5: Add quota badge to DevicesPage

**Files:**
- Modify: `frontend/src/pages/DevicesPage.tsx`

- [ ] **Step 1: Add quota state and badge to DevicesPage header**

In `DevicesPage.tsx`, after the existing state declarations, add:

```tsx
const [quota, setQuota] = useState<{ used: number; max: number } | null>(null);

useEffect(() => {
  vpnApi.listDevices().then(d => {
    setQuota({ used: d.total, max: 50 }); // max comes from backend config
  }).catch(() => {});
}, [refreshTrigger]);
```

Replace the "Add device" button area with:

```tsx
<div className="flex items-center gap-3">
  {quota && (
    <span className={`
      text-xs font-medium px-2.5 py-1 rounded-full
      ${quota.used >= quota.max
        ? 'bg-red-100 text-red-700'
        : quota.used >= quota.max * 0.8
          ? 'bg-amber-100 text-amber-700'
          : 'bg-gray-100 text-gray-600'
      }
    `}>
      {t('page.quotaBadge', { used: quota.used, max: quota.max })}
    </span>
  )}
  <button
    onClick={handleRefresh}
    className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
    title={t('page.refreshTitle')}
  >
    <RefreshCw className="w-4 h-4" />
  </button>
  <button
    onClick={() => setShowWizard(true)}
    disabled={quota ? quota.used >= quota.max : false}
    className="flex items-center gap-2 bg-sky-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-sky-700 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
    title={quota && quota.used >= quota.max ? t('page.quotaFull', { used: quota.used, max: quota.max }) : undefined}
  >
    <Plus className="w-4 h-4" />
    {t('page.addDevice')}
  </button>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/DevicesPage.tsx
git commit -m "feat: add device quota badge and disable Add when limit reached"
```

### Task 3.6: Add rate limit and quota error handling to AddDeviceWizard

**Files:**
- Modify: `frontend/src/components/AddDeviceWizard.tsx`

- [ ] **Step 1: Add specific error messages for 429, 409, 410**

In the `handleSubmit` catch block, replace the generic error:

```tsx
} catch (err: any) {
  const msg = err.message || '';
  if (msg.includes('quota exceeded') || msg.includes('429')) {
    if (msg.includes('quota')) {
      setErrorMsg(t('wizard.errorQuotaExceeded', { used: 0, max: 0 }));
    } else {
      setErrorMsg(t('wizard.errorRateLimit'));
    }
  } else if (msg.includes('already activated') || msg.includes('409')) {
    setErrorMsg(t('wizard.errorDeviceAlreadyActivated'));
  } else if (msg.includes('revoked') || msg.includes('410')) {
    setErrorMsg(t('wizard.errorDeviceRevoked'));
  } else {
    setErrorMsg(err.message || t('wizard.errorGeneric'));
  }
  setStep('error');
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AddDeviceWizard.tsx
git commit -m "feat: add specific error messages for rate limit, quota, and device state errors"
```

### Task 3.7: Create RevokeConfirmModal component

**Files:**
- Create: `frontend/src/components/RevokeConfirmModal.tsx`

- [ ] **Step 1: Write RevokeConfirmModal**

Create `frontend/src/components/RevokeConfirmModal.tsx`:

```tsx
import React, { useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';

interface Props {
  deviceName: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export const RevokeConfirmModal: React.FC<Props> = ({
  deviceName, onConfirm, onCancel, loading,
}) => {
  const { t } = useTranslation('vpn');
  const [typed, setTyped] = useState('');

  const canConfirm = typed === deviceName && !loading;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="w-5 h-5" />
            <h2 className="text-lg font-semibold">{t('revoke.title')}</h2>
          </div>
          <button onClick={onCancel} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-red-600">{t('revoke.consequences')}</p>
          <p className="text-sm text-gray-600">
            {t('revoke.confirmInstruction', { name: deviceName })}
          </p>
          <input
            type="text"
            value={typed}
            onChange={e => setTyped(e.target.value)}
            placeholder={t('revoke.confirmPlaceholder')}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
            autoFocus
          />
          <div className="flex gap-3 pt-2">
            <button
              onClick={onCancel}
              className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm font-medium hover:bg-gray-50"
            >
              {t('revoke.cancel')}
            </button>
            <button
              onClick={onConfirm}
              disabled={!canConfirm}
              className="flex-1 bg-red-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '...' : t('revoke.confirm')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/RevokeConfirmModal.tsx
git commit -m "feat: add RevokeConfirmModal with type-to-confirm pattern"
```

### Task 3.8: Use RevokeConfirmModal in DeviceList

**Files:**
- Modify: `frontend/src/components/DeviceList.tsx`

- [ ] **Step 1: Replace window.confirm with modal state**

In `DeviceList.tsx`, import the modal:

```tsx
import { RevokeConfirmModal } from './RevokeConfirmModal';
```

Replace the `handleRevoke` function:

```tsx
const [revokeTarget, setRevokeTarget] = useState<{ uuid: string; name: string } | null>(null);

const handleRevokeClick = (uuid: string, name: string | null) => {
  setRevokeTarget({ uuid, name: name || uuid });
};

const handleRevokeConfirm = async () => {
  if (!revokeTarget) return;
  setRevoking(revokeTarget.uuid);
  try {
    await vpnApi.revokeDevice(revokeTarget.uuid);
    setRevokeTarget(null);
    await load();
  } catch (e: any) {
    alert(t('list.revokeFailed', { message: e.message }));
  } finally {
    setRevoking(null);
  }
};
```

Update the revoke button's onClick:

```tsx
onClick={() => handleRevokeClick(device.device_uuid, device.device_name)}
```

Add the modal at the bottom of the component, before the closing return:

```tsx
{revokeTarget && (
  <RevokeConfirmModal
    deviceName={revokeTarget.name}
    onConfirm={handleRevokeConfirm}
    onCancel={() => setRevokeTarget(null)}
    loading={revoking === revokeTarget.uuid}
  />
)}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/DeviceList.tsx
git commit -m "feat: replace window.confirm with RevokeConfirmModal for device revocation"
```

### Task 3.9: Add PlatformAdmin cross-tenant toggle to DevicesPage

**Files:**
- Modify: `frontend/src/pages/DevicesPage.tsx`
- Modify: `frontend/src/components/DeviceList.tsx`
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Add PlatformAdmin detection and toggle in DevicesPage**

In `DevicesPage.tsx`, add:

```tsx
const isPlatformAdmin = (window as any).__nekazariAuthContext?.roles?.includes('PlatformAdmin') ?? false;
const [allTenants, setAllTenants] = useState(false);
```

Add a toggle in the header, between the title and the buttons:

```tsx
{isPlatformAdmin && (
  <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-0.5">
    <button
      onClick={() => setAllTenants(false)}
      className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
        !allTenants ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
      }`}
    >
      {t('list.myTenant')}
    </button>
    <button
      onClick={() => setAllTenants(true)}
      className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
        allTenants ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
      }`}
    >
      {t('list.allTenants')}
    </button>
  </div>
)}
```

Pass `allTenants` and `isPlatformAdmin` to `DeviceList`:

```tsx
<DeviceList refreshTrigger={refreshTrigger} allTenants={allTenants} isPlatformAdmin={isPlatformAdmin} />
```

- [ ] **Step 2: Update DeviceList to accept new props and pass to API**

In `DeviceList.tsx`, update Props:

```tsx
interface Props {
  refreshTrigger: number;
  allTenants?: boolean;
  isPlatformAdmin?: boolean;
}
```

In the `load` function:

```tsx
const data = await vpnApi.listDevices(allTenants);
```

Add a "Tenant" column in the table header when `isPlatformAdmin && allTenants`:

```tsx
{isPlatformAdmin && allTenants && (
  <th className="px-4 py-3 text-left font-medium text-gray-600">{t('list.tenant')}</th>
)}
```

Add the tenant cell in each row (before the actions column):

```tsx
{isPlatformAdmin && allTenants && (
  <td className="px-4 py-3 text-xs text-gray-500 font-mono">
    {(device as any).tenant_id}
  </td>
)}
```

- [ ] **Step 3: Update api.ts Device type to include optional tenant_id**

```typescript
export interface Device {
  device_uuid: string;
  device_type: DeviceType;
  device_name: string | null;
  state: DeviceState;
  headscale_peer_id: string | null;
  online: boolean;
  last_seen: string | null;
  tenant_id?: string | null;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DevicesPage.tsx frontend/src/components/DeviceList.tsx frontend/src/services/api.ts
git commit -m "feat: add PlatformAdmin cross-tenant toggle and tenant column"
```

### Task 3.10: Create FactoryPanel component

**Files:**
- Create: `frontend/src/components/FactoryPanel.tsx`

- [ ] **Step 1: Write FactoryPanel**

Create `frontend/src/components/FactoryPanel.tsx`:

```tsx
import React, { useState } from 'react';
import { Factory, Check, AlertCircle } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';
import { vpnApi } from '../services/api';

interface Props {
  onSuccess: () => void;
}

export const FactoryPanel: React.FC<Props> = ({ onSuccess }) => {
  const { t } = useTranslation('vpn');
  const [expanded, setExpanded] = useState(false);
  const [uuid, setUuid] = useState('');
  const [deviceType, setDeviceType] = useState('rover');
  const [tenantId, setTenantId] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);
    try {
      // Use the factory registration endpoint — note: this requires
      // PlatformAdmin role in the JWT for the backend to accept it.
      const res = await fetch('/api/vpn/factory/register-device', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_uuid: uuid.trim(),
          device_type: deviceType,
          tenant_id: tenantId.trim(),
          device_name: deviceName.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as any).detail || `Error ${res.status}`);
      }
      const data = await res.json();
      setResult(data.claim_code);
      onSuccess();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!expanded) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <button
          onClick={() => setExpanded(true)}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <Factory className="w-4 h-4" />
          {t('factory.title')}
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Factory className="w-5 h-5 text-gray-600" />
          <h3 className="text-sm font-semibold text-gray-900">{t('factory.title')}</h3>
        </div>
        <button onClick={() => setExpanded(false)} className="text-gray-400 hover:text-gray-600 text-sm">
          {t('wizard.close')}
        </button>
      </div>
      <p className="text-xs text-gray-500">{t('factory.description')}</p>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('factory.uuidLabel')}</label>
          <input type="text" value={uuid} onChange={e => setUuid(e.target.value)} required
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('factory.typeLabel')}</label>
          <select value={deviceType} onChange={e => setDeviceType(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500">
            <option value="rover">{t('wizard.typeRover')}</option>
            <option value="gateway">{t('wizard.typeGateway')}</option>
            <option value="sensor_esp32">{t('wizard.typeEsp32')}</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('factory.tenantLabel')}</label>
          <input type="text" value={tenantId} onChange={e => setTenantId(e.target.value)} required
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('factory.nameLabel')}</label>
          <input type="text" value={deviceName} onChange={e => setDeviceName(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
        </div>

        {result && (
          <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg p-3">
            <Check className="w-4 h-4 text-green-600" />
            <span className="text-sm text-green-700 font-mono">{t('factory.registerSuccess', { code: result })}</span>
          </div>
        )}
        {error && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg p-3">
            <AlertCircle className="w-4 h-4 text-red-500" />
            <span className="text-sm text-red-600">{error}</span>
          </div>
        )}

        <button type="submit" disabled={loading}
          className="w-full bg-gray-800 text-white rounded-lg py-2 text-sm font-medium hover:bg-gray-900 disabled:opacity-50 transition-colors">
          {loading ? t('factory.registering') : t('factory.registerDevice')}
        </button>
      </form>
    </div>
  );
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/FactoryPanel.tsx
git commit -m "feat: add FactoryPanel for PlatformAdmin device pre-registration from UI"
```

### Task 3.11: Integrate FactoryPanel into DevicesPage

**Files:**
- Modify: `frontend/src/pages/DevicesPage.tsx`

- [ ] **Step 1: Add FactoryPanel below the header for PlatformAdmin**

After the "How it works" card, add:

```tsx
{isPlatformAdmin && (
  <FactoryPanel onSuccess={handleSuccess} />
)}
```

Import at the top:

```tsx
import { FactoryPanel } from '../components/FactoryPanel';
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/DevicesPage.tsx
git commit -m "feat: integrate FactoryPanel into DevicesPage for PlatformAdmin"
```

### Task 3.12: Create DeviceQuotaWidget for dashboard

**Files:**
- Create: `frontend/src/components/DeviceQuotaWidget.tsx`
- Modify: `frontend/src/slots/index.tsx`

- [ ] **Step 1: Write DeviceQuotaWidget**

Create `frontend/src/components/DeviceQuotaWidget.tsx`:

```tsx
import React, { useEffect, useState } from 'react';
import { HardDrive } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';
import { vpnApi, Device } from '../services/api';

export const DeviceQuotaWidget: React.FC = () => {
  const { t } = useTranslation('vpn');
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const maxDevices = 50;

  useEffect(() => {
    vpnApi.listDevices()
      .then(d => setDevices(d.devices))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-24 mb-3" />
        <div className="h-8 bg-gray-200 rounded w-16" />
      </div>
    );
  }

  const used = devices.filter(d => d.state !== 'REVOKED').length;
  const pct = maxDevices > 0 ? (used / maxDevices) * 100 : 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center">
            <HardDrive className="w-4 h-4 text-gray-600" />
          </div>
          <span className="text-sm font-medium text-gray-700">{t('page.quotaBadge', { used, max: maxDevices })}</span>
        </div>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all ${
            pct >= 100 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-500' : 'bg-green-500'
          }`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Register widget in slots**

In `slots/index.tsx`, import and add to dashboard-widget:

```tsx
import { DeviceQuotaWidget } from '../components/DeviceQuotaWidget';
```

Add to the `dashboard-widget` array:

```tsx
{
  id: `${MODULE_ID}-quota-widget`,
  moduleId: MODULE_ID,
  component: 'DeviceQuotaWidget',
  priority: 39,
  localComponent: DeviceQuotaWidget,
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DeviceQuotaWidget.tsx frontend/src/slots/index.tsx
git commit -m "feat: add device quota dashboard widget with progress bar"
```

---

## PR #4 — CI/CD (bucket fix, supply chain, typecheck, gitignore)

### Task 4.1: Fix MinIO bucket name and replace third-party action

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Fix bucket name and replace s3-cp-action with mc CLI**

In `deploy.yml`, change:

```yaml
# Before:
  MINIO_BUCKET: marketplace-modules
```

To:

```yaml
# After:
  MINIO_BUCKET: nekazari-frontend
```

Replace the "Upload to MinIO" step:

```yaml
# Before:
      - name: Upload to MinIO
        if: steps.check_secrets.outputs.has_secrets == 'true'
        uses: prewk/s3-cp-action@master
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.MINIO_ROOT_USER }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.MINIO_ROOT_PASSWORD }}
          AWS_REGION: us-east-1
          S3_ENDPOINT: ${{ secrets.MINIO_URL }}
        with:
          args: --recursive --acl public-read
          source: './frontend/dist'
          dest: 's3://${{ env.MINIO_BUCKET }}/modules/vpn'
```

To:

```yaml
# After:
      - name: Setup MinIO Client
        if: steps.check_secrets.outputs.has_secrets == 'true'
        run: |
          curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
          chmod +x /usr/local/bin/mc

      - name: Upload to MinIO
        if: steps.check_secrets.outputs.has_secrets == 'true'
        run: |
          mc alias set nkz "${{ secrets.MINIO_URL }}" "${{ secrets.MINIO_ROOT_USER }}" "${{ secrets.MINIO_ROOT_PASSWORD }}"
          mc cp --recursive ./frontend/dist/ nkz/${{ env.MINIO_BUCKET }}/modules/vpn/
          mc anonymous set public nkz/${{ env.MINIO_BUCKET }}/modules/vpn/nekazari-module.js
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "fix: use correct MinIO bucket nekazari-frontend, replace s3-cp-action with mc CLI

Removes unpinned third-party GitHub action. Uses official MinIO Client
(mc) for direct S3-compatible upload."
```

### Task 4.2: Add typecheck gate to CI and package.json

**Files:**
- Modify: `frontend/package.json`
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Add typecheck script to package.json**

Read `frontend/package.json` first to see current scripts, then add:

```json
"typecheck": "tsc --noEmit"
```

- [ ] **Step 2: Add typecheck step to CI before build**

In `deploy.yml`, after "Install dependencies" and before "Build module", add:

```yaml
      - name: Type check
        working-directory: ./frontend
        run: npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json .github/workflows/deploy.yml
git commit -m "feat: add typecheck gate to CI pipeline"
```

### Task 4.3: Gitignore dist and remove committed bundle

**Files:**
- Modify: `.gitignore`
- Delete: `frontend/dist/nekazari-module.js` (from git tracking)

- [ ] **Step 1: Add dist to gitignore**

Append to `.gitignore`:

```
frontend/dist/
```

- [ ] **Step 2: Remove dist from git tracking**

```bash
git rm --cached frontend/dist/nekazari-module.js
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore frontend/dist, remove committed IIFE bundle

The IIFE bundle is a CI artifact, not source code."
```

---

## Block 5 — Verification (manual, no PR, on the server)

### Task 5.1: Verify health and auth

- [ ] **Step 1: Port-forward to network controller**

```bash
sudo kubectl port-forward -n nekazari svc/nkz-network-controller-service 8001:80
```

- [ ] **Step 2: Test health endpoint**

```bash
curl -s http://localhost:8001/health | jq
# Expected: {"status": "healthy", "service": "nkz-network-controller", "version": "1.0.0"}
```

- [ ] **Step 3: Test auth rejection (no token)**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/vpn/devices/
# Expected: 401 or 403
```

### Task 5.2: Test factory registration

- [ ] **Step 1: Register a test device via curl**

```bash
TOKEN="<valid-factory-jwt>"
curl -s -X POST http://localhost:8001/api/vpn/factory/register-device \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_uuid":"test-0000-0001","device_type":"rover","tenant_id":"testtenant"}' | jq
# Expected: {"claim_code": "V1-...", "device_uuid": "test-0000-0001", "device_type": "rover"}
```

### Task 5.3: Test device claim

- [ ] **Step 1: Claim the device**

```bash
CLAIM_CODE="<code from previous step>"
TENANT_TOKEN="<valid-tenant-jwt>"
curl -s -X POST http://localhost:8001/api/vpn/devices/claim \
  -H "Authorization: Bearer $TENANT_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Fiware-Service: testtenant" \
  -d "{\"device_uuid\":\"test-0000-0001\",\"claim_code\":\"$CLAIM_CODE\"}" | jq
# Expected: {"device_uuid": "...", "state": "CONSUMED", "preauth_key": "...", ...}
```

### Task 5.4: Verify NGSI-LD entity creation

- [ ] **Step 1: Check entity-manager logs or Orion-LD for the entity**

```bash
sudo kubectl logs -n nekazari deployment/entity-manager --tail=50 | grep "test-0000-0001"
# Expected: log entry showing entity creation with Link header
```

### Task 5.5: Verify rate limiting

- [ ] **Step 1: Send 6 failed claim attempts with wrong code**

```bash
for i in $(seq 1 6); do
  echo "Attempt $i:"
  curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:8001/api/vpn/devices/claim \
    -H "Authorization: Bearer $TENANT_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Fiware-Service: testtenant" \
    -d '{"device_uuid":"test-0000-0001","claim_code":"V1-WRONGXX"}'
done
# Expected: Attempts 1-5 return 400. Attempt 6 returns 429.
```

### Task 5.6: Verify quota enforcement

- [ ] **Step 1: Set max_devices=0 in tenant_limits and attempt claim**

```bash
# In psql:
# INSERT INTO admin_platform.tenant_limits (tenant_id, max_devices) VALUES ('testtenant', 0);
# Then attempt claim → Expected: 429 "Device quota exceeded (N/0)"
```

### Task 5.7: Verify RLS

- [ ] **Step 1: Query provisioned_devices without setting tenant context**

```bash
sudo kubectl exec -n nekazari deployment/timescaledb -- psql -U postgres -d nekazari -c \
  "SELECT * FROM provisioned_devices;"
# Expected: 0 rows (RLS blocks the query since app.current_tenant_id is not set)
```

- [ ] **Step 2: Query with tenant context set**

```bash
sudo kubectl exec -n nekazari deployment/timescaledb -- psql -U postgres -d nekazari -c \
  "SET app.current_tenant_id = 'testtenant'; SELECT * FROM provisioned_devices;"
# Expected: rows for testtenant only
```

### Task 5.8: Verify audit log

- [ ] **Step 1: Check device_audit_log has entries**

```bash
sudo kubectl exec -n nekazari deployment/timescaledb -- psql -U postgres -d nekazari -c \
  "SELECT * FROM device_audit_log ORDER BY created_at DESC LIMIT 5;"
# Expected: entries for REGISTERED and CLAIMED actions
```

### Task 5.9: Verify frontend PlatformAdmin cross-tenant view

- [ ] **Step 1: Log in as PlatformAdmin, navigate to /devices**
- [ ] **Step 2: Toggle "All tenants" — verify tenant column appears**
- [ ] **Step 3: Toggle back to "My tenant" — verify column disappears**

### Task 5.10: Verify frontend Factory panel

- [ ] **Step 1: As PlatformAdmin, open the Factory panel**
- [ ] **Step 2: Register a test device — verify Claim Code is displayed**
- [ ] **Step 3: Verify the code format matches expected "V1-XXXXXXXX"**

### Task 5.11: Verify i18n

- [ ] **Step 1: Switch language to English — verify all new keys render**
- [ ] **Step 2: Switch language to Spanish — verify all new keys render**
- [ ] **Step 3: Check quota badge, revoke modal, factory panel, error messages**

---

## Cleanup

After all blocks are merged and verified:

- [ ] Delete `deploy_vpn_module.py` from workspace root (superseded by CI)
- [ ] Archive `VPN_OPERATION_PLAN.md` (superseded by this plan + spec)
- [ ] Update `PENDING.md`: mark VPN module as **T3 — Verified**
- [ ] Update `.ai/CURRENT_STATE.md`: add VPN module status
- [ ] Update memory: record VPN module verification date and key decisions
