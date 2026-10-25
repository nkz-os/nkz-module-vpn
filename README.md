# Device Management (`vpn`) — Nekazari Platform module

Zero-touch provisioning of field devices — robots, gateways and sensors — over a
self-hosted [Headscale](https://github.com/juanfont/headscale) tailnet.

1. **Factory.** A platform operator registers the device for the organisation it is built
   for and prints the claim code on the chassis. Sensors also get a certificate signed by the
   platform IoT CA (MQTT over mTLS).
2. **Claim.** The organisation's administrator enters the device UUID and claim code in the
   *Devices* page. The module creates the device's twin in the context broker and, for robots
   and gateways, a single-use Headscale pre-auth key tagged `tag:field-device`.
3. **Join.** The device runs one `tailscale up` command and joins the tailnet. The tailnet
   policy lets `tag:field-device` reach only the platform's Zenoh router (7447) and MQTT
   broker (1883) through the cluster's subnet router; devices never see each other.

## Architecture

```
UI (Module Federation remote, route /devices)
   │  ${VITE_API_URL}/api/vpn/...   (session cookie)
   ▼
api-gateway ── signed tenant headers ──► vpn backend (FastAPI)
robotics ───── X-Internal-Service-Secret ──► /api/vpn/internal/*
                                              │
        ┌───────────────┬─────────────────────┼──────────────┬───────────────┐
        ▼               ▼                     ▼              ▼               ▼
  PostgreSQL       Headscale API         Orion-LD          Redis        cert-manager
  (own database,   (users, tagged        (SDM twin:        (claim rate   (device
   forced RLS)      pre-auth keys,        ManufacturingMachine  limiting)  certificates)
                    nodes)                for robots, Device)
```

- **Source of truth:** the module's own PostgreSQL database (`devices`, `device_events`), with
  row-level security forced per organisation. Claim codes are never stored: a code is
  `V{n}-` + Base32(HMAC-SHA256(factory secret v{n}, device UUID))[:8] and is recomputed to
  validate it, so a device re-registered with the same UUID keeps its printed code.
- **Twin:** on claim the module upserts an NGSI-LD entity with official Smart Data Models
  terms only (`name`, `serialNumber`, `deviceState`, and `category: robot` for robots). No
  provisioning data reaches the broker.
- **State machine:** `PENDING → CLAIMED → REVOKED` (or `PENDING → REVOKED`). Revoking removes
  the device's node from Headscale and expires its key if still unused; if Headscale cannot be
  reached nothing changes. Sensors get no VPN key (they use MQTT over mTLS).
- **Auth:** user routes require the gateway's `X-Auth-Signature`; internal routes require
  `X-Internal-Service-Secret`. Wrong claim codes are rate limited per device and per
  organisation (successful activations never count), and claims are refused if the limiter
  is unavailable.

## API (`/api/vpn`)

| Route | Role | Purpose |
|---|---|---|
| `POST /factory/register-device` | PlatformAdmin | Register a device for an organisation; returns its claim code |
| `POST /factory/sign-csr` | PlatformAdmin | Sign the device CSR (CN = UUID, OU = type); returns certificate and CA |
| `POST /devices/validate` | TenantAdmin, PlatformAdmin | Check a claim code without side effects |
| `POST /devices/claim` | TenantAdmin, PlatformAdmin | Claim: twin + single-use pre-auth key (shown once) |
| `GET /devices` | TenantAdmin, PlatformAdmin | List (`?all_tenants=true` for PlatformAdmin) with live VPN state |
| `GET /devices/{uuid}`, `/devices/{uuid}/events` | TenantAdmin, PlatformAdmin | Detail and audit trail |
| `DELETE /devices/{uuid}` | TenantAdmin, PlatformAdmin | Revoke |
| `GET /internal/devices/{uuid}` | internal secret | Lookup for other platform services |

## Development

```bash
# backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
docker run -d -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=postgres postgres:14
TEST_POSTGRES_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres python -m pytest tests/
ruff check app tests

# frontend
pnpm install && pnpm typecheck && pnpm test
pnpm build:module      # dist/remoteEntry.js, dist/mf-manifest.json, dist/manifest.json
```

Backend configuration is environment only (see `backend/app/config.py`); the service refuses
to start if a required value is missing. Database migrations run with
`python -m app.db.migrate` (an init container in Kubernetes).

## Deployment

Push to `main`: CI tests the backend against PostgreSQL, builds the image
`ghcr.io/<org>/nkz-module-vpn/network-controller` and publishes the frontend through the
platform's OIDC publish workflow. `k8s/` holds reference manifests and the registration SQL;
the deployment's own configuration repository pins the image digest.

Devices: see [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md).

## License

AGPL-3.0-only. See [LICENSE](LICENSE).
