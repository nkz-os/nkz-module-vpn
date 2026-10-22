"""
Modelos SQLAlchemy para el Network Controller.
"""

import uuid as _uuid
from sqlalchemy import Column, String, Integer, Text, TIMESTAMP, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ProvisionedDevice(Base):
    """Registro de cada dispositivo IoT provisionado en la plataforma."""

    __tablename__ = "provisioned_devices"

    uuid = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    device_type = Column(String, nullable=False)
    device_name = Column(String, nullable=True)
    claim_code_hash = Column(String, nullable=False)
    claim_version = Column(Integer, nullable=False)
    state = Column(String, nullable=False, default="PENDING")
    headscale_peer_id = Column(String, nullable=True)
    cert_fingerprint = Column(String, nullable=True)
    ngsi_entity_id = Column(String, nullable=True)
    provisioned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


# Canonical mapping: device_type → FIWARE Smart Data Model type
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
    action = Column(String, nullable=False)
    actor_sub = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
