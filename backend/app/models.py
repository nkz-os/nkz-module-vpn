"""
Modelos SQLAlchemy para el Network Controller.
"""

import uuid as _uuid
from sqlalchemy import Column, String, Integer, Text, TIMESTAMP, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ProvisionedDevice(Base):
    """
    Registro de cada dispositivo IoT provisionado en la plataforma.

    Flujo de estados:
        PENDING   → El dispositivo está registrado en fábrica, esperando activación.
        CONSUMED  → El Tenant Admin introdujo el Claim Code y el dispositivo hizo call-home.
        REVOKED   → El dispositivo fue revocado manualmente (perdido, comprometido, etc.).

    Tipos de dispositivo:
        rover         → Robot autónomo KLinux + Tailscale. Tendrá headscale_peer_id.
        gateway       → Gateway KLinux + Tailscale. Tendrá headscale_peer_id.
        sensor_esp32  → Sensor ESP32 con mTLS directo. Tendrá cert_fingerprint. NO Tailscale.
    """

    __tablename__ = "provisioned_devices"

    uuid = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    device_type = Column(
        String, nullable=False
    )  # rover | gateway | sensor_esp32
    device_name = Column(String, nullable=True)  # Nombre amigable puesto por el tenant

    # Claim Code (seguridad)
    claim_code_hash = Column(String, nullable=False)  # HMAC almacenado, nunca el código en claro
    claim_version = Column(Integer, nullable=False)    # Versión de la Factory Secret usada

    # Estado del ciclo de vida
    state = Column(String, nullable=False, default="PENDING")  # PENDING | CONSUMED | REVOKED

    # Campos específicos por tipo de dispositivo
    headscale_peer_id = Column(String, nullable=True)  # NULL para sensor_esp32
    cert_fingerprint = Column(String, nullable=True)   # NULL para rover/gateway

    # Entidad NGSI-LD creada al provisionar
    ngsi_entity_id = Column(String, nullable=True)  # urn:ngsi-ld:Robot:<uuid>

    # Timestamps
    provisioned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# Canonical mapping: device_type → FIWARE Smart Data Model type
# Single source of truth used by routes and entity_manager.
DEVICE_TYPE_TO_NGSI_TYPE: dict[str, str] = {
    "rover": "AgriRobot",
    "gateway": "AgriGateway",
    "sensor_esp32": "AgriSensor",
}


class DeviceAuditLog(Base):
    """Immutable audit trail for device lifecycle events."""

    __tablename__ = "device_audit_log"

    id = Column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tenant_id = Column(String, nullable=False, index=True)
    device_uuid = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)  # REGISTERED | CLAIMED | REVOKED
    actor_sub = Column(String, nullable=False)  # JWT sub claim
    ip_address = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
