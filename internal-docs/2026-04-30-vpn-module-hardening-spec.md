---
title: VPN Module Hardening — Design Spec
description: SOTA security hardening, tenant isolation, and production readiness for the nkz-module-vpn (Zero-Touch Provisioning via Headscale SDN)
---

## Context

Full audit completed 2026-04-30. The module is architecturally sound (HMAC Claim Codes + Headscale SDN + PKI cert-manager) but has 4 critical, 4 high, 5 medium, and 3 low issues blocking production. This spec defines the hardening work.

**Out of scope**: Headscale core infrastructure (`nkz/k8s/vpn/`), K8s Secrets creation, IoT CA generation, firewall rules, subnet router setup — these are platform infrastructure responsibilities.

## Architecture (unchanged)

```
Frontend (IIFE) → api-gateway (cookie→Bearer) → nkz-network-controller
                                                      │
                    ┌─────────────────────────────────┼─────────────────────────────┐
                    │                                 │                             │
              Headscale SDN                   PostgreSQL + RLS              entity-manager
              (per-tenant users)              (row-level security)           (NGSI-LD)
```

## Block 1 — Critical Fixes

### 1.1 JWT Issuer Resolution (C1)

**Problem**: `auth.py` uses raw `settings.JWT_ISSUER` (default `""`) in 3 places. The `jwt_issuer_url` property exists on `Settings` but is never called. If `JWT_ISSUER` is unset, JWKS URL becomes `/protocol/openid-connect/certs` (relative, broken).

**Fix**:
- Replace all 3 usages of `settings.JWT_ISSUER` with `settings.jwt_issuer_url` in `auth.py`
- Remove `JWT_ISSUER` field from `Settings` (keep only the property)
- If neither `KEYCLOAK_URL` nor `JWT_ISSUER` is configured, raise at startup

**Files**: `backend/app/auth.py:22,38,51`, `backend/app/config.py:21`

### 1.2 NGSI-LD Context Compliance (C2)

**Problem**: `entity_manager.py` sends `Content-Type: application/json` without a `Link` header pointing to the NGSI-LD `@context`. Per the strict FIWARE mandate in CLAUDE.md, this violates the platform standard.

**Fix**: Add `Link` header with the NGSI-LD context URL before every POST to entity-manager:
```
Link: <{CONTEXT_URL}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"
```
Add `CONTEXT_URL` env var to `Settings` (default: `http://api-gateway-service:5000/ngsi-ld-context.json`) and wire it into the K8s deployment manifest.

**Files**: `backend/app/services/entity_manager.py`, `backend/app/config.py`, `k8s/deployment.yaml`

### 1.3 Unified SDM-Compliant Type Mapping (C4, H2)

**Problem**: Type mapping is split between `routes/devices.py` and `services/entity_manager.py` with divergent lists. `rover → AgriculturalRobot` is not a standard FIWARE SDM type.

**Fix**: Single source of truth — `DEVICE_TYPE_TO_NGSI_TYPE` dict in `models.py`:

| `device_type` | NGSI-LD type (SDM) | Domain |
|---|---|---|
| `rover` | `AgriRobot` | AgriFood |
| `gateway` | `AgriGateway` | AgriFood |
| `sensor_esp32` | `AgriSensor` | AgriFood |

Both routes and entity_manager read from this dict. Remove the inline normalization logic from `entity_manager.py`.

**Files**: `backend/app/models.py`, `backend/app/routes/devices.py`, `backend/app/routes/factory.py`, `backend/app/services/entity_manager.py`

## Block 2 — Tenant Isolation

### 2.1 Rate Limiting (H1)

**Problem**: `config.py` defines `REDIS_URL`, `CLAIM_RATE_LIMIT_ATTEMPTS`, `CLAIM_RATE_LIMIT_WINDOW_SECONDS` but the `/devices/claim` endpoint has no limiter.

**Fix**:
- Add `slowapi` or custom Redis-based rate limiter middleware
- Apply to `/api/vpn/devices/claim`: 5 attempts per tenant per hour, 10 attempts per IP per hour
- `/health` endpoint exempt from all rate limiting (K8s probes)

**Files**: `backend/app/middleware/rate_limit.py` (new), `backend/app/routes/devices.py`, `backend/requirements.txt`

### 2.2 Device Quotas via tenant_limits

**Problem**: No limit on devices per tenant.

**Fix**: Before activating/registering a device, query `admin_platform.tenant_limits.max_devices` for the tenant. If current count (PENDING + CONSUMED) >= limit, reject with HTTP 429 and message `"Device quota exceeded (N/N)"`.

**Files**: `backend/app/services/tenant_limits.py` (new), `backend/app/routes/devices.py`, `backend/app/routes/factory.py`

### 2.3 Row-Level Security (PostgreSQL)

**Problem**: No defense in depth at the database level. A code bug could leak devices cross-tenant.

**Fix**: SQL migration enabling RLS on `provisioned_devices`:
```sql
ALTER TABLE provisioned_devices ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON provisioned_devices
  FOR ALL
  USING (tenant_id = current_setting('app.current_tenant_id'));
```
The backend sets `app.current_tenant_id` at the start of every request via a FastAPI middleware, after JWT validation extracts the tenant.

**Files**: `backend/migrations/001_rls_devices.sql` (new), `backend/app/middleware/tenant_context.py` (new), `backend/app/main.py`

### 2.4 Headscale ACL Groups per Tenant

**Problem**: ACLs are static. All field devices share `tag:field-device`. No intra-tenant network isolation.

**Fix**: When the network-controller creates a Headscale user for a tenant, it also generates a `tag:tenant-<tenant_id>` tag. Devices claimed by that tenant get the tag. The ACL policy is extended to scope accept rules by tenant tag. The controller needs RBAC permissions to update the `headscale-config` ConfigMap.

**Files**: `backend/app/services/headscale.py`, `k8s/deployment.yaml` (RBAC for ConfigMap)

### 2.5 Audit Log

**Problem**: No record of who activated/revoked what device or when.

**Fix**: New table `device_audit_log` with columns: `id (UUID PK)`, `tenant_id`, `device_uuid`, `action (CLAIMED | REVOKED | REGISTERED)`, `actor_sub (JWT sub)`, `ip_address`, `created_at`. Written on every write operation. Queryable by PlatformAdmin.

**Files**: `backend/app/models.py`, `backend/app/services/audit.py` (new), `backend/app/routes/devices.py`, `backend/app/routes/factory.py`

## Block 3 — Frontend

### 3.1 API Client Auth (H3)

**Problem**: `api.ts` tries `__NKZ_SDK__?.auth?.getToken()` and `__nekazariAuth?.token` but neither exists with cookie auth.

**Fix**: Remove token logic. Use `credentials: 'include'` for cookie propagation. Add `X-Tenant-ID` header from `window.__nekazariAuthContext.tenantId`.

**Files**: `frontend/src/services/api.ts`

### 3.2 Hardcoded Strings (M1)

**Problem**: Two components have English strings not using `t()`.

**Fix**: Replace with i18n keys already present in locale files. `VpnContextPanel.tsx:104` → `t('context.lastSeen', { date })`. `VpnStatusWidget.tsx:39` → `t('widget.loadError')`.

**Files**: `frontend/src/components/VpnContextPanel.tsx`, `frontend/src/components/VpnStatusWidget.tsx`

### 3.3 Tenant Admin UX — Quota & Rate Limit Feedback

**New additions**:
- **Quota badge**: in `DevicesPage` header, shows `"3/50 devices"`. Amber at >80%, red at 100%. "Add device" button disabled at quota limit with explanatory tooltip.
- **Rate limit feedback**: `AddDeviceWizard` shows specific error for 429 rate-limit responses, including remaining block time if available.
- **Revocation confirmation**: replace `window.confirm()` with a modal that requires typing the device name to confirm. Shows clear consequences.

**Files**: `frontend/src/pages/DevicesPage.tsx`, `frontend/src/components/AddDeviceWizard.tsx`, `frontend/src/components/DeviceList.tsx`

### 3.4 Platform Admin UX

**New additions**:
- **Cross-tenant toggle**: visible only for PlatformAdmin role. Toggle "All tenants / My tenant" in `DevicesPage` header. In "All tenants" mode, table shows an additional `Tenant` column. Default: "My tenant".
- **Global quota dashboard widget**: shows total platform devices, tenants near quota (>80%), tenants with zero devices.
- **Factory panel**: collapsible panel (PlatformAdmin only) for pre-registering devices from the UI without the CLI tool. Calls the existing `/api/vpn/factory/register-device` endpoint.

**Files**: `frontend/src/pages/DevicesPage.tsx`, `frontend/src/components/DeviceQuotaWidget.tsx` (new), `frontend/src/components/FactoryPanel.tsx` (new), `frontend/src/components/RevokeConfirmModal.tsx` (new)

### 3.5 Slot Entity Types

**Fix**: Update `showWhen.entityType` in `slots/index.tsx` from `['Robot', 'AgriRobot', 'Rover', 'IoTGateway']` to `['AgriRobot', 'AgriGateway', 'AgriSensor']` matching the unified SDM types.

**Files**: `frontend/src/slots/index.tsx`

### 3.6 i18n

**New keys** (added to `es.json` + `en.json`):
- `page.quotaBadge`, `page.quotaFull`, `page.quotaWarning`
- `wizard.errorRateLimit`, `wizard.errorQuotaExceeded`, `wizard.errorDeviceAlreadyActivated`, `wizard.errorDeviceRevoked`
- `list.tenant`, `list.allTenants`, `list.myTenant`
- `factory.title`, `factory.description`, `factory.registerDevice`, `factory.registerSuccess`
- `revoke.title`, `revoke.confirmInstruction`, `revoke.consequences`, `revoke.confirmPlaceholder`

**Files**: `frontend/src/locales/es.json`, `frontend/src/locales/en.json`

## Block 4 — CI/CD

### 4.1 MinIO Bucket Name (C3)

**Problem**: CI uses `MINIO_BUCKET: marketplace-modules`. The actual bucket is `nekazari-frontend`.

**Fix**: Change to `MINIO_BUCKET: nekazari-frontend` with dest path `modules/vpn/`.

**Files**: `.github/workflows/deploy.yml`

### 4.2 Supply Chain (H4)

**Problem**: `prewk/s3-cp-action@master` is an unpinned third-party action.

**Fix**: Replace with `minio/mc` CLI in a run step. No external action needed.

**Files**: `.github/workflows/deploy.yml`

### 4.3 Typecheck Gate

**Fix**: Add `npm run typecheck` (`tsc --noEmit`) step before build. Add script to `package.json`.

**Files**: `.github/workflows/deploy.yml`, `frontend/package.json`

### 4.4 Gitignore dist

**Fix**: Add `dist/` to `.gitignore`. Remove currently committed `dist/nekazari-module.js` from the repo.

**Files**: `.gitignore`

## Block 5 — Verification (manual, no PR)

1. `kubectl port-forward` to nkz-network-controller, test `/health`, auth, `/api/vpn/devices/`
2. Register a test device via factory endpoint (curl or Factory panel UI)
3. Claim it from the frontend wizard → verify success response with preauth_key
4. Verify NGSI-LD entity created in Orion-LD with correct SDM type and `Link` context header
5. Verify rate limiting: 5+ failed claim attempts → blocked with 429
6. Verify quota: attempt to register device N+1 → rejected with 429 + message
7. Verify RLS: direct DB query without `app.current_tenant_id` returns 0 rows from `provisioned_devices`
8. Verify audit log: check `device_audit_log` has entries for each action
9. Verify PlatformAdmin cross-tenant toggle works and shows correct tenant column
10. Verify PlatformAdmin factory panel pre-registers devices correctly
11. Verify i18n: switch language, confirm all new keys render correctly

## Failure Modes & Edge Cases

| Scenario | Behavior |
|---|---|
| Headscale unreachable during claim | Claim succeeds locally; entity-manager call is best-effort. Device is CONSUMED in BD. Operator may need to re-sync. |
| entity-manager unreachable | Same as above. Entity can be created manually via platform UI. |
| Tenant quota reached while factory pre-registers | Factory registration allowed (state PENDING, not counted). Quota only enforced at claim time. |
| JWT expired during claim | 401 — frontend redirects to Keycloak login via api-gateway. |
| Concurrent claim of same device | Second request gets 409 Conflict (device already CONSUMED). |
| Device revoked then re-claimed | Not supported. Revoked is terminal. Factory must issue new device with new UUID. |
| Tenant deleted from Keycloak | Headscale user and devices remain as orphaned data. Cleanup handled by tenant-webhook (out of scope). |
| Factory Secret v1 compromised | Rotate to v2: add `FACTORY_SECRET_V2` to K8s Secret, bump `FACTORY_SECRET_CURRENT_VERSION=2`. Existing V1 devices continue working (version stored per-device). |
