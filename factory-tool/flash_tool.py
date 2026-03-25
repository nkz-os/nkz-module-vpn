#!/usr/bin/env python3
"""
NKZ Factory Tool — Estación de flasheo de dispositivos IoT.

Uso:
    python flash_tool.py provision \
        --uuid <DEVICE_UUID> \
        --type rover|gateway|sensor_esp32 \
        --tenant <TENANT_ID> \
        --api-url https://nkz.YOUR_DOMAIN \
        --token <FACTORY_JWT_TOKEN> \
        --out-dir ./output/<uuid>/

Qué hace:
    1. Genera par de claves RSA-2048 localmente.
    2. Genera un CSR con el UUID como Common Name.
    3. Envía el CSR al endpoint /api/vpn/factory/sign-csr.
    4. Pre-registra el dispositivo en /api/vpn/factory/register-device.
    5. Guarda en --out-dir:
        - device.key   (clave privada — NUNCA subir a git)
        - device.crt   (certificado firmado por la CA IoT)
        - claim_code.txt (imprimir en el chasis)
    6. Para ESP32: genera también un header .h con los valores en formato C.

El Claim Code generado por el servidor (ej. V1-NKZ8492X) se imprime en el chasis
y es el único mecanismo de activación del dispositivo desde la UI.
"""

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_keypair() -> tuple[rsa.RSAPrivateKey, str]:
    """Genera un par de claves RSA-2048 y devuelve (private_key, private_key_pem)."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return private_key, key_pem


def generate_csr(private_key: rsa.RSAPrivateKey, device_uuid: str, device_type: str) -> str:
    """
    Genera un CSR con:
        CN = <device_uuid>
        O  = Nekazari
        OU = <device_type>
    """
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, device_uuid),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nekazari"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, device_type),
            ])
        )
        .sign(private_key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def sign_csr_remote(
    csr_pem: str, device_uuid: str, device_type: str, api_url: str, token: str
) -> str:
    """Envía el CSR al nkz-network-controller y recibe el certificado firmado."""
    url = f"{api_url.rstrip('/')}/api/vpn/factory/sign-csr"
    r = httpx.post(
        url,
        json={"csr_pem": csr_pem, "device_uuid": device_uuid, "device_type": device_type},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"ERROR signing CSR: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    return r.json()["certificate_pem"]


def register_device_remote(
    device_uuid: str, device_type: str, tenant_id: str,
    device_name: str | None, api_url: str, token: str
) -> str:
    """Registra el dispositivo en la BD y devuelve el Claim Code."""
    url = f"{api_url.rstrip('/')}/api/vpn/factory/register-device"
    body = {
        "device_uuid": device_uuid,
        "device_type": device_type,
        "tenant_id": tenant_id,
    }
    if device_name:
        body["device_name"] = device_name

    r = httpx.post(
        url,
        json=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=15,
    )
    if r.status_code != 201:
        print(f"ERROR registering device: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    return r.json()["claim_code"]


def write_esp32_header(out_dir: Path, key_pem: str, cert_pem: str, ca_cert_pem: str) -> None:
    """
    Genera un archivo .h con los certificados en formato C para ESP32 (NVS/SPIFFS).
    Solo para device_type == 'sensor_esp32'.
    """
    def pem_to_c_string(pem: str) -> str:
        lines = pem.strip().split("\n")
        return "\n".join(f'    "{line}\\n"' for line in lines)

    header = textwrap.dedent(f"""\
        // NKZ Device Credentials — GENERADO AUTOMATICAMENTE por factory tool
        // NO COMMITEAR — contiene clave privada del dispositivo
        #pragma once

        static const char* NKZ_DEVICE_PRIVATE_KEY = \\
        {pem_to_c_string(key_pem)};

        static const char* NKZ_DEVICE_CERTIFICATE = \\
        {pem_to_c_string(cert_pem)};

        static const char* NKZ_CA_CERTIFICATE = \\
        {pem_to_c_string(ca_cert_pem)};
    """)
    (out_dir / "nkz_credentials.h").write_text(header)
    print(f"  ESP32 header: {out_dir}/nkz_credentials.h")


def provision(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nProvisioning device: {args.uuid} ({args.type})")
    print("=" * 50)

    # 1. Generar par de claves
    print("1. Generating RSA-2048 keypair...")
    private_key, key_pem = generate_keypair()

    # 2. Generar CSR
    print("2. Generating CSR...")
    csr_pem = generate_csr(private_key, args.uuid, args.type)

    # 3. Firmar CSR remotamente
    print("3. Sending CSR to NKZ Network Controller for signing...")
    cert_pem = sign_csr_remote(csr_pem, args.uuid, args.type, args.api_url, args.token)
    print("   Certificate signed OK.")

    # 4. Registrar dispositivo y obtener Claim Code
    print("4. Registering device in platform...")
    claim_code = register_device_remote(
        args.uuid, args.type, args.tenant, getattr(args, "name", None), args.api_url, args.token
    )
    print(f"   Claim Code: {claim_code}")

    # 5. Guardar archivos
    print(f"5. Saving output to {out_dir}/")
    (out_dir / "device.key").write_text(key_pem)
    (out_dir / "device.crt").write_text(cert_pem)
    (out_dir / "claim_code.txt").write_text(f"{claim_code}\n")

    # 6. Para ESP32: generar header .h
    if args.type == "sensor_esp32":
        ca_cert_path = Path(args.ca_cert) if hasattr(args, "ca_cert") and args.ca_cert else None
        ca_cert_pem = ca_cert_path.read_text() if ca_cert_path and ca_cert_path.exists() else ""
        write_esp32_header(out_dir, key_pem, cert_pem, ca_cert_pem)

    print("\nDone!")
    print(f"  Private key : {out_dir}/device.key")
    print(f"  Certificate : {out_dir}/device.crt")
    print(f"  Claim Code  : {claim_code}  ← IMPRIMIR EN EL CHASIS")
    print("\nWARNING: device.key es la clave privada del dispositivo.")
    print("         Flashear en el dispositivo y destruir la copia local.")


def main() -> None:
    parser = argparse.ArgumentParser(description="NKZ Factory Tool")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("provision", help="Provision a new device")
    p.add_argument("--uuid", required=True, help="Hardware UUID (MAC, serial, etc.)")
    p.add_argument("--type", required=True, choices=["rover", "gateway", "sensor_esp32"])
    p.add_argument("--tenant", required=True, help="Tenant ID")
    p.add_argument("--api-url", required=True, help="NKZ API base URL")
    p.add_argument("--token", required=True, help="Factory JWT token")
    p.add_argument("--out-dir", required=True, help="Output directory")
    p.add_argument("--name", help="Human-readable device name")
    p.add_argument("--ca-cert", help="Path to IoT CA certificate (for ESP32 header)")

    args = parser.parse_args()
    if args.command == "provision":
        provision(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
