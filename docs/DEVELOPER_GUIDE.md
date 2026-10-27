---
title: Zero-Touch Provisioning (VPN) — Developer Guide
description: How manufacturers and integrators prepare field devices to join the Nekazari platform through its self-hosted Headscale tailnet
---
# Zero-Touch Provisioning (VPN) — Developer Guide

For hardware manufacturers, integrators and robotics developers who build devices that
connect to a Nekazari platform installation.

## 1. What the device gets

A robot or gateway joins the platform's tailnet (WireGuard, coordinated by Headscale) and can
then reach, through the cluster's subnet router:

- the **Zenoh router** on TCP 7447 (robot ↔ platform link), and
- the **MQTT broker** on TCP 1883 (management and slow telemetry).

Nothing else: devices cannot reach each other or any other cluster service. The address of
each service is handed out by the module that owns it (for example the robotics module
returns its Zenoh endpoint when a robot is enrolled).

Sensors that cannot run a VPN client connect to the MQTT broker over TLS with the client
certificate issued at the factory instead.

## 2. Device requirements

- An OS that runs the standard Tailscale client (`tailscaled`): Linux (Debian/Ubuntu,
  Raspberry Pi OS, Yocto, Alpine), and others.
- Outbound internet access on TCP 443. No inbound ports.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

## 3. Factory

A platform operator (PlatformAdmin) provisions each unit with `factory-tool/flash_tool.py`:

```bash
export NKZ_FACTORY_TOKEN=<PLATFORM_ADMIN_ACCESS_TOKEN>   # not on the command line
python factory-tool/flash_tool.py provision \
  --uuid <DEVICE_UUID> --type rover|gateway|sensor --tenant <ORGANISATION_ID> \
  --api-url https://<platform-api> --out-dir ./output/<DEVICE_UUID>/
```

It registers the device for the organisation it is built for, generates the key pair and CSR
locally, has the certificate signed, and writes `device.key` (mode 0600), `device.crt`,
`ca.crt`, `claim_code.txt` and `nkz-device.json`. Print the claim code on the chassis; flash
the key and certificate, then destroy the local copy of the key.

The claim code is bound to the device UUID. It is the only thing the organisation needs to
activate the device. The tool writes `claim_code.txt` as soon as the device is registered; if
a later step fails, running it again for the same device returns the same code.

## 4. Activation in the field

1. The organisation's administrator opens **Devices → Add device** and enters the UUID and
   claim code.
2. For robots and gateways the page shows a single-use key (valid for 30 minutes, shown
   once) and the exact command to run on the device:

   ```bash
   sudo tailscale up --login-server=<login server> --authkey=<key> \
     --hostname=<DEVICE_UUID> --accept-routes
   ```

   `--accept-routes` is required: without it the Linux client ignores the cluster route
   announced by the subnet router. `--hostname` must be the device UUID — the platform uses it
   to recognise the node.
3. The device appears **online** in the Devices page with its tailnet address.

If the key expired before the device joined (or was not copied), use **New key** on the
device in the Devices page: it expires the old key and shows a new command. It is only
offered while the device has not joined.

Verify on the device:

```bash
tailscale status          # the subnet router is listed as a peer
ip route get <zenoh-ip>   # goes through tailscale0
```

## 5. Revocation

Revoking a device in the page removes its node from the tailnet immediately, expires its VPN
key if it was never used, and marks it as revoked; the claim code can no longer be used. A
revoked unit needs a new registration with a new UUID.
