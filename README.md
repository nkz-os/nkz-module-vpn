# Nekazari VPN Module — Zero-Touch Provisioning via Headscale SDN

Device management module for the Nekazari platform. Provides secure, zero-touch provisioning of IoT field devices (rovers, gateways, ESP32 sensors) using HMAC Claim Codes and Headscale WireGuard mesh networking.

## Architecture

```
Operator (UI) → nkz-network-controller (FastAPI) → Headscale SDN (WireGuard mesh)
                              ↕
                   PostgreSQL + TimescaleDB
                   (RLS per tenant)
```

## Features

- **Zero-Touch Provisioning (ZTP)** — activate devices with a Claim Code printed on the chassis; no config files needed
- **HMAC Claim Codes** — factory-generated, one-time-use, timing-safe validation with versioned secrets
- **Headscale SDN** — WireGuard mesh with NAT traversal (STUN/DERP), per-tenant ACL groups
- **mTLS PKI** — cert-manager signs X.509 certificates for ESP32 sensors
- **Row-Level Security** — PostgreSQL RLS ensures strict tenant isolation at the database level
- **Rate limiting** — Redis-backed, 5 attempts per tenant per hour on the claim endpoint
- **Device quotas** — per-tenant limits from `admin_platform.tenant_limits`; enforced at claim time
- **Audit log** — immutable trail of REGISTERED, CLAIMED, and REVOKED events with actor and IP
- **i18n** — Spanish (es) + English (en)

## Quick Start

### Prerequisites

- Headscale deployed and accessible at `http://headscale-service:8080`
- PostgreSQL database `nekazari` with `provisioned_devices` and `device_audit_log` tables
- Redis server with authentication
- Keycloak realm with `nekazari-frontend` client and `tenant_id` mapper
- K8s secrets: `nkz-network-controller-secret` (headscale-api-key, factory-secret-v1), `redis-secret` (password)

### Building

```bash
# Backend Docker image
docker build -t ghcr.io/nkz-os/nkz-module-vpn/network-controller:latest backend/

# Frontend IIFE bundle
cd frontend && npm install && npm run build:module
# Upload dist/nekazari-module.js to MinIO bucket nekazari-frontend at modules/vpn/
```

### Deploying

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/registration.sql  # one-time: registers module in marketplace_modules
```

Apply the RLS migration manually:

```bash
psql -h <host> -U postgres -d nekazari -f backend/migrations/001_rls_devices.sql
```

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Health check |
| `GET` | `/api/vpn/devices/` | TenantAdmin/PlatformAdmin | List tenant devices (`?all_tenants=true` for PlatformAdmin) |
| `POST` | `/api/vpn/devices/claim` | TenantAdmin/PlatformAdmin | Activate device with Claim Code (rate-limited) |
| `GET` | `/api/vpn/devices/{uuid}/status` | TenantAdmin/PlatformAdmin | Real-time device status from Headscale |
| `DELETE` | `/api/vpn/devices/{uuid}` | TenantAdmin/PlatformAdmin | Revoke device |
| `GET` | `/api/vpn/devices/{uuid}/audit-log` | PlatformAdmin or owning tenant | Audit trail for a device |
| `POST` | `/api/vpn/factory/register-device` | Factory/PlatformAdmin | Pre-register device, return Claim Code |
| `POST` | `/api/vpn/factory/sign-csr` | Factory/PlatformAdmin | Sign device CSR with IoT CA (CLI-only) |
| `GET` | `/api/vpn/peers` | TenantAdmin/PlatformAdmin | (deprecated) List Headscale peers |

## Device Lifecycle

```
Factory:   flash_tool.py → /factory/sign-csr → /factory/register-device → Claim Code on chassis
Operator:  UI "Add device" → enter UUID + Claim Code → /devices/claim → preauth key shown
Device:    tailscale up --login-server=https://vpn.robotika.cloud --authkey=<KEY>
Platform:  device online in Headscale → status visible in UI → can be revoked if compromised
```

## Tenant Isolation

- **Database**: Row-Level Security — every query filtered by `app.current_tenant_id`
- **Rate limiting**: per-tenant Redis counters (5 claims/hour)
- **Quotas**: per-tenant device limit from `admin_platform.tenant_limits`
- **Headscale**: per-tenant users, ACL tags `tag:tenant-<id>`

## License

AGPL-3.0 — see [LICENSE](LICENSE)
