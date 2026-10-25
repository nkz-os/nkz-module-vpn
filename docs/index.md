---
title: "Device Management"
description: "Zero-touch provisioning of field devices over the platform's self-hosted VPN."
sidebar:
  order: 1
---

# Device Management

Activate robots, gateways and sensors with the claim code printed on their chassis.

- **Factory registration:** each device is registered for its organisation and gets a claim
  code (and, for sensors, an MQTT client certificate).
- **Claim:** the organisation's administrator enters the device UUID and claim code. Robots
  and gateways receive a single-use VPN key and the command to run on the device.
- **Network:** devices join the platform's Headscale tailnet and can reach only the
  platform's Zenoh router and MQTT broker. They never see each other.
- **Twin:** every claimed device appears in the context broker as an official Smart Data
  Models entity (`ManufacturingMachine` for robots, `Device` for sensors and gateways).
- **Revocation** removes the device from the network immediately.

Integrators: see the [developer guide](DEVELOPER_GUIDE.md).
