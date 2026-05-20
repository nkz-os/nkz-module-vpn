"""
Modelos locales.
"""

# Canonical mapping: device_type → FIWARE Smart Data Model type
# Single source of truth used by routes and entity_manager.
DEVICE_TYPE_TO_NGSI_TYPE: dict[str, str] = {
    "rover": "AgriRobot",
    "gateway": "AgriGateway",
    "sensor_esp32": "AgriSensor",
}
