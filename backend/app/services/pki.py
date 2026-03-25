"""
Servicio PKI: firma CSRs de dispositivos via cert-manager (CertificateRequest).

El factory tool genera el par de claves y el CSR localmente (en la estación
de fábrica). Este servicio recibe el CSR, crea un CertificateRequest en K8s,
cert-manager lo firma con la CA IoT y devuelve el certificado X.509 en PEM.

El certificado firmado se incrusta en el dispositivo antes de salir de fábrica.
"""

import asyncio
import base64
import logging
from datetime import datetime

from kubernetes import client as k8s_client, config as k8s_config
from kubernetes.client.rest import ApiException

from app.config import settings

logger = logging.getLogger(__name__)

# Tiempo máximo de espera para que cert-manager firme el certificado
_SIGN_TIMEOUT_SECONDS = 30
_SIGN_POLL_INTERVAL = 1.0


def _load_k8s_config() -> None:
    """Carga la config de K8s (in-cluster cuando corre en K8s, local para tests)."""
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()


async def sign_csr(csr_pem: str, device_uuid: str, device_type: str) -> str:
    """
    Firma un CSR con la CA IoT de Nekazari.

    Args:
        csr_pem: CSR en formato PEM (generado por el factory tool).
        device_uuid: UUID del dispositivo (para nombrar el CertificateRequest).
        device_type: rover | gateway | sensor_esp32.

    Returns:
        Certificado X.509 firmado en formato PEM.

    Raises:
        TimeoutError: si cert-manager no firma en _SIGN_TIMEOUT_SECONDS.
        RuntimeError: si cert-manager rechaza el CSR.
    """
    _load_k8s_config()
    custom_api = k8s_client.CustomObjectsApi()

    # Nombre único y legible para el CertificateRequest
    cr_name = f"device-{device_uuid[:12]}-{int(datetime.utcnow().timestamp())}"

    cr_body = {
        "apiVersion": "cert-manager.io/v1",
        "kind": "CertificateRequest",
        "metadata": {
            "name": cr_name,
            "namespace": settings.K8S_NAMESPACE,
            "labels": {
                "app": "nkz-network-controller",
                "device-uuid": device_uuid,
                "device-type": device_type,
            },
        },
        "spec": {
            "request": base64.b64encode(csr_pem.encode()).decode(),
            "issuerRef": {
                "name": settings.IOT_CA_ISSUER,
                "kind": "ClusterIssuer",
            },
            "duration": settings.DEVICE_CERT_DURATION,
            "isCA": False,
            "usages": ["client auth", "digital signature", "key encipherment"],
        },
    }

    try:
        custom_api.create_namespaced_custom_object(
            group="cert-manager.io",
            version="v1",
            namespace=settings.K8S_NAMESPACE,
            plural="certificaterequests",
            body=cr_body,
        )
        logger.info(f"CertificateRequest {cr_name} created for device {device_uuid}")
    except ApiException as e:
        raise RuntimeError(f"Failed to create CertificateRequest: {e}") from e

    # Esperar a que cert-manager firme el certificado (polling)
    cert_pem = await _wait_for_certificate(custom_api, cr_name)

    # Limpiar el CertificateRequest (ya no es necesario)
    try:
        custom_api.delete_namespaced_custom_object(
            group="cert-manager.io",
            version="v1",
            namespace=settings.K8S_NAMESPACE,
            plural="certificaterequests",
            name=cr_name,
        )
    except ApiException:
        pass  # La limpieza falla silenciosamente — no es crítico

    return cert_pem


async def _wait_for_certificate(
    custom_api: k8s_client.CustomObjectsApi, cr_name: str
) -> str:
    """Polling hasta que cert-manager firme el certificado o se agote el timeout."""
    elapsed = 0.0
    while elapsed < _SIGN_TIMEOUT_SECONDS:
        await asyncio.sleep(_SIGN_POLL_INTERVAL)
        elapsed += _SIGN_POLL_INTERVAL

        try:
            cr = custom_api.get_namespaced_custom_object(
                group="cert-manager.io",
                version="v1",
                namespace=settings.K8S_NAMESPACE,
                plural="certificaterequests",
                name=cr_name,
            )
        except ApiException:
            continue

        status = cr.get("status", {})
        conditions = status.get("conditions", [])

        # Comprobar si cert-manager rechazó el CSR
        for cond in conditions:
            if cond.get("type") == "Denied" and cond.get("status") == "True":
                raise RuntimeError(
                    f"CertificateRequest {cr_name} was denied: {cond.get('message')}"
                )

        # Comprobar si el certificado ya está firmado
        cert_b64 = status.get("certificate")
        if cert_b64:
            return base64.b64decode(cert_b64).decode("utf-8")

    raise TimeoutError(
        f"cert-manager did not sign CertificateRequest {cr_name} "
        f"within {_SIGN_TIMEOUT_SECONDS}s"
    )
