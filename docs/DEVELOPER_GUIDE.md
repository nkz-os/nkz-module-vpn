# Nekazari Zero-Touch Provisioning (VPN) — Developer Guide

This document explains how hardware manufacturers, integrators, and robotics developers must configure their field devices (robots, tractors, gateways) to securely connect to the Nekazari Cloud Platform using our Software-Defined Network (SDN).

## 1. Architecture Overview (Headscale / Tailscale)

Nekazari uses **Headscale** (an open-source, self-hosted Tailscale control server) to provide a Zero-Trust mesh network. This allows your device to securely connect to the central ROS2/Zenoh broker and MQTT services without opening firewall ports, port-forwarding, or dealing with complex static IPs.

### Important Notice on Legacy MQTT Devices
> **Will my existing MQTT devices stop working?**
> **No.** If you have simple IoT sensors or gateways currently connecting to our public MQTT broker using standard TLS/SSL and username/password credentials, **they will continue to function normally**. The VPN is an *optional* (but highly recommended for robotics and ROS/Zenoh telemetry) layer that runs in parallel.

## 2. Device Requirements

Your device must run an operating system capable of running the standard **Tailscale client** (`tailscaled`).
- **Supported OS:** Linux (Ubuntu, Debian, Yocto, Raspberry Pi OS, Alpine), Windows, macOS, Android, iOS.
- **Network:** Outbound internet access (port 443 TCP for control plane, port 41641/3478 UDP for STUN/TURN/DERP relays, and 51820 UDP for direct peer-to-peer). **No inbound ports need to be opened.**

## 3. How to install the Client

Install the official Tailscale client on your Linux-based robot or gateway:

```bash
# For Ubuntu / Debian / ROS environments
curl -fsSL https://tailscale.com/install.sh | sh
```

For other operating systems or manual installation, refer to the [official Tailscale installation guide](https://tailscale.com/download).

## 4. The Zero-Touch Provisioning (ZTP) Flow

We use a "Claim Code" approach. You do **not** configure usernames, passwords, or static IPs on the robot.

### Step 1: Generate a Claim Code in the Factory
During your device's manufacturing or flashing process, you must generate or obtain a unique **Claim Code** (e.g., `NKZ-1234-ABCD`). 
*(Note: A dedicated flashing tool `factory-tool/flash_tool.py` is provided in our repository for bulk generation of HMAC-signed codes).*

### Step 2: The Device connects to Nekazari
On the robot's first boot in the field, run the following command to point the Tailscale client to the Nekazari Headscale server instead of the public Tailscale servers.

```bash
# Replace 'https://vpn.nkz.robotika.cloud' with the actual production URL of the Nekazari SDN
sudo tailscale up --login-server=https://vpn.nkz.robotika.cloud
```

### Step 3: Registration
When you run the command above, Tailscale will output an authentication URL in the terminal, looking something like this:
```text
To authenticate, visit:
https://vpn.nkz.robotika.cloud/register/nodekey:xyz123...
```

**Do NOT visit this URL.**
Instead, the end-user (the farmer or operator) will log into the Nekazari Web Platform, navigate to the **Devices** module, and enter the **Claim Code** printed on the robot's physical sticker.

Behind the scenes, Nekazari will match the Claim Code to the Tenant, automatically approve the `nodekey` in Headscale, and generate the Digital Twin (`AgriculturalMachine`) in the FIWARE Context Broker.

### Step 4: Verification
Once the user claims the device in the web UI, the `tailscale up` command on the robot will complete successfully.
The robot is now part of the mesh network and has been assigned an internal IP address (e.g., `100.64.0.5`).

You can verify the connection status on the device:
```bash
tailscale status
```

## 5. Network Access (Zero-Trust Policies)

Once connected, your device is placed in a strictly isolated Tenant environment. 

By default, Nekazari's network policies (`acls.hujson`) only allow outbound traffic from your device to the central cluster infrastructure on specific ports:
- **Zenoh Router:** `100.64.0.1:7447` (Telemetry, ROS2 bridge)
- **MQTT Broker:** `100.64.0.1:1883` (Management, slow data)

*Note: The exact IP `100.64.0.1` is an example of the central cluster's router IP. Check the platform documentation for the exact endpoints assigned to your Tenant.*

Your device **cannot** ping or access other devices in the network, not even devices belonging to the same Tenant, unless explicitly authorized via a custom ACL policy requested by the Tenant Administrator.
