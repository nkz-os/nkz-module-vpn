"""
Device certificates signed by the IoT CA through cert-manager.

The factory tool generates the key pair and CSR on the flashing station; this
service checks that the CSR names the registered device (CN = device UUID,
OU = device type — the CN becomes the MQTT username on the mTLS listener),
creates a CertificateRequest against the IoT ClusterIssuer and returns the
signed certificate together with the CA certificate cert-manager reports in
the request status (CA issuer), so no Secret has to be read.
"""

import asyncio
import base64
import logging
import time
from dataclasses import dataclass

from cryptography import x509
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)

_SIGN_TIMEOUT_SECONDS = 30
_POLL_INTERVAL_SECONDS = 1.0
_GROUP, _VERSION, _PLURAL = "cert-manager.io", "v1", "certificaterequests"


@dataclass(frozen=True)
class SignedCertificate:
    certificate_pem: str
    ca_pem: str


class PkiError(Exception):
    pass


def _attr(name: x509.Name, oid) -> str | None:
    values = name.get_attributes_for_oid(oid)
    return str(values[0].value) if values else None


def validate_csr(csr_pem: str, device_uuid: str, device_type: str) -> None:
    """Raise ValueError unless the CSR is well signed and names this device."""
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    except Exception:
        raise ValueError("CSR is not valid PEM") from None
    if not csr.is_signature_valid:
        raise ValueError("CSR signature is invalid")
    if _attr(csr.subject, NameOID.COMMON_NAME) != device_uuid:
        raise ValueError("CSR common name must be the device UUID")
    if _attr(csr.subject, NameOID.ORGANIZATIONAL_UNIT_NAME) != device_type:
        raise ValueError("CSR organizational unit must be the device type")


def fingerprint_sha256(certificate_pem: str) -> str:
    from cryptography.hazmat.primitives import hashes

    cert = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"))
    return cert.fingerprint(hashes.SHA256()).hex()


class Pki:
    def __init__(self, namespace: str, issuer: str, duration: str):
        self._namespace = namespace
        self._issuer = issuer
        self._duration = duration
        self._api = None

    def _custom_api(self):
        if self._api is None:
            from kubernetes import client, config

            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            self._api = client.CustomObjectsApi()
        return self._api

    async def sign_csr(self, csr_pem: str, device_uuid: str, device_type: str) -> SignedCertificate:
        return await asyncio.to_thread(self._sign_blocking, csr_pem, device_uuid, device_type)

    def _sign_blocking(self, csr_pem: str, device_uuid: str, device_type: str) -> SignedCertificate:
        from kubernetes.client.rest import ApiException

        api = self._custom_api()
        name = f"device-{device_uuid[:12]}-{int(time.time())}"
        body = {
            "apiVersion": f"{_GROUP}/{_VERSION}",
            "kind": "CertificateRequest",
            "metadata": {"name": name, "namespace": self._namespace,
                         "labels": {"app": "vpn-backend", "device-type": device_type}},
            "spec": {
                "request": base64.b64encode(csr_pem.encode("utf-8")).decode("ascii"),
                "issuerRef": {"name": self._issuer, "kind": "ClusterIssuer", "group": _GROUP},
                "duration": self._duration,
                "isCA": False,
                "usages": ["client auth", "digital signature", "key encipherment"],
            },
        }
        try:
            api.create_namespaced_custom_object(_GROUP, _VERSION, self._namespace, _PLURAL, body)
        except ApiException as exc:
            raise PkiError(f"CertificateRequest create failed: HTTP {exc.status}") from None
        try:
            deadline = time.monotonic() + _SIGN_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                time.sleep(_POLL_INTERVAL_SECONDS)
                try:
                    cr = api.get_namespaced_custom_object(_GROUP, _VERSION, self._namespace, _PLURAL, name)
                except ApiException:
                    continue
                status = cr.get("status") or {}
                for cond in status.get("conditions") or []:
                    if cond.get("type") in ("Denied", "InvalidRequest") and cond.get("status") == "True":
                        raise PkiError(f"CertificateRequest {cond.get('type').lower()}: {cond.get('reason')}")
                if status.get("certificate"):
                    return SignedCertificate(
                        certificate_pem=base64.b64decode(status["certificate"]).decode("utf-8"),
                        ca_pem=base64.b64decode(status.get("ca") or b"").decode("utf-8"),
                    )
            raise PkiError(f"CertificateRequest not signed within {_SIGN_TIMEOUT_SECONDS}s")
        finally:
            try:
                api.delete_namespaced_custom_object(_GROUP, _VERSION, self._namespace, _PLURAL, name)
            except ApiException as exc:
                logger.warning("CertificateRequest %s cleanup failed: HTTP %s", name, exc.status)
