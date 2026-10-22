# Nekazari VPN Module — Zero-Touch Provisioning via Headscale SDN

Device management module for the Nekazari platform. Provides secure, zero-touch provisioning of IoT field devices (rovers, gateways, ESP32 sensors) using HMAC Claim Codes and Headscale WireGuard mesh networking.

## Architecture

```
Operator (UI) → API Gateway → nkz-network-controller (FastAPI) → Headscale SDN
                                      ↕
                                  Orion-LD (NGSI-LD)
                        (Zero Direct Writes Architecture)
```

## Features

- **Module Federation 2.0** — frontend integrated seamlessly as a remote into the core platform using `@nekazari/module-kit`.
- **Zero-Touch Provisioning (ZTP)** — activate devices with a Claim Code printed on the chassis; no config files needed.
- **Strict NGSI-LD Compliance** — zero direct database writes. All device state is synced securely using FIWARE Smart Data Models via `OrionClient`.
- **HMAC Claim Codes** — factory-generated, one-time-use, timing-safe validation with versioned secrets.
- **Headscale SDN** — WireGuard mesh with NAT traversal (STUN/DERP), per-tenant ACL groups.
- **mTLS PKI** — cert-manager signs X.509 certificates for ESP32 sensors.
- **Rate limiting** — Redis-backed, 5 attempts per tenant per hour on the claim endpoint.
- **i18n** — Spanish (es) + English (en).

## Quick Start

### Prerequisites

- Headscale deployed and accessible at `http://headscale-service:8080`
- Orion-LD running as the central Context Broker
- Redis server with authentication
- Keycloak realm with `nekazari-frontend` client and `tenant_id` mapper
- K8s secrets: `nkz-network-controller-secret` (headscale-api-key, factory-secret-v1), `redis-secret` (password)

### Building

```bash
# Backend Docker image
docker build -t ghcr.io/nkz-os/nkz-module-vpn/network-controller:latest backend/

# Frontend (MF2)
pnpm install && pnpm run build
# Upload dist/ folder to MinIO bucket nekazari-frontend at modules/nkz-module-vpn/
```

### Deploying (GitOps)

Managed entirely via **ArgoCD**.
Manifests reside in `nkz/gitops/modules/vpn.yaml`. Wait for ArgoCD to sync the application state with the cluster.

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Health check |
| `GET` | `/api/vpn/devices/` | Gateway | List tenant devices from Orion-LD |
| `POST` | `/api/vpn/devices/claim` | Gateway | Activate device with Claim Code (rate-limited) |
| `GET` | `/api/vpn/devices/{uuid}/status` | Gateway | Real-time device status from Headscale |
| `DELETE` | `/api/vpn/devices/{uuid}` | Gateway | Revoke device in Orion-LD & Headscale |
| `POST` | `/api/vpn/factory/register-device` | Gateway | Pre-register device, return Claim Code |
| `POST` | `/api/vpn/factory/sign-csr` | Gateway | Sign device CSR with IoT CA |

## License

AGPL-3.0 — see [LICENSE](LICENSE)
