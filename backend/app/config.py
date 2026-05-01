"""
NKZ Network Controller — Configuration

All deployment-specific values (domains, URLs, secrets) must be provided
via environment variables or Kubernetes Secrets — never hardcoded here.
"""

import os

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "NKZ Network Controller"

    # Base de datos
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@timescaledb:5432/nekazari"

    # Keycloak — validación JWT (set via env var or K8s ConfigMap)
    KEYCLOAK_URL: str = "http://keycloak:8080/auth"
    KEYCLOAK_REALM: str = "nekazari"
    JWT_ALGORITHM: str = "RS256"

    @property
    def jwt_issuer_url(self) -> str:
        """Derive issuer from KEYCLOAK_URL + realm, or from explicit JWT_ISSUER env var."""
        explicit = os.getenv("JWT_ISSUER", "")
        if explicit:
            return explicit
        if self.KEYCLOAK_URL:
            return f"{self.KEYCLOAK_URL}/realms/{self.KEYCLOAK_REALM}"
        raise RuntimeError(
            "Neither JWT_ISSUER nor KEYCLOAK_URL is configured. "
            "The service cannot validate tokens without an issuer URL."
        )

    @property
    def jwks_url(self) -> str:
        return f"{self.jwt_issuer_url}/protocol/openid-connect/certs"

    # Headscale — plano de control SDN
    HEADSCALE_API_URL: str = "http://headscale-service:8080"
    HEADSCALE_PUBLIC_URL: str = ""   # URL externa que los dispositivos usan: https://vpn.DOMAIN — must be set via env
    HEADSCALE_API_KEY: str  # Requerido. Desde Secret 'nkz-network-controller-secret'

    # Factory Secret para HMAC claim codes (versionado)
    FACTORY_SECRET_V1: str  # Requerido. Desde Secret 'nkz-network-controller-secret'
    FACTORY_SECRET_CURRENT_VERSION: int = 1

    # Redis — rate limiting en endpoint /claim
    REDIS_URL: str = "redis://redis-service:6379/0"
    CLAIM_RATE_LIMIT_ATTEMPTS: int = 5
    CLAIM_RATE_LIMIT_WINDOW_SECONDS: int = 3600

    # cert-manager — namespace y ClusterIssuer
    K8S_NAMESPACE: str = "nekazari"
    IOT_CA_ISSUER: str = "nekazari-iot-ca"
    DEVICE_CERT_DURATION: str = "8760h"

    # CORS — set via CORS_ORIGINS env var (comma-separated or JSON list)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Entity Manager — para crear entidades NGSI-LD al activar dispositivos
    ENTITY_MANAGER_URL: str = "http://entity-manager-service:5000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
