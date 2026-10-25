"""
Device Management Backend - Configuration

Environment-based configuration using pydantic-settings. Every deployment
value comes from the environment; defaults are empty so nothing here names a
real installation.
"""

import json
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Application
    app_name: str = "Device Management"
    app_version: str = "2.0.0"
    debug: bool = False
    log_level: str = "INFO"  # level for this module's own loggers; see app.logging_setup

    # API
    api_prefix: str = "/api/vpn"
    # Comma-separated (platform ConfigMap) or a JSON list; empty = no CORS headers.
    cors_origins: str = ""

    # Internal service-to-service auth (/internal/* routes). Compared with
    # hmac.compare_digest — NOT the api-gateway X-Auth-Signature format.
    internal_service_secret: str = ""

    # Gateway signature check on user routes. The SDK's require_auth reads
    # REQUIRE_HMAC_SIGNATURE / HMAC_SECRET itself; these fields only make the
    # service refuse to start when the check would silently be off.
    require_hmac_signature: bool = True
    hmac_secret: str = ""

    # Own database nkz_vpn (devices + audit). No fallback DSN.
    postgres_url: str = ""

    # Headscale control plane.
    headscale_api_url: str = ""
    headscale_public_url: str = ""  # login server the devices use
    headscale_api_key: str = ""

    # Claim codes: one secret per version, V1 first.
    factory_secret_v1: str = ""
    factory_secret_current_version: int = 1

    # Pre-auth keys handed out at claim time.
    preauth_ttl_minutes: int = 30

    # Claim rate limiting (Redis).
    redis_url: str = ""
    redis_password: str = ""
    claim_limit_per_device: int = 5
    claim_limit_per_tenant: int = 5
    claim_limit_per_ip: int = 10
    claim_window_seconds: int = 3600

    # Device certificates (cert-manager).
    k8s_namespace: str = "nekazari"
    iot_ca_issuer: str = "nekazari-iot-ca"
    device_cert_duration: str = "8760h"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return []
        if raw.startswith("["):
            return [str(o).strip() for o in json.loads(raw) if str(o).strip()]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def validate_required(self) -> None:
        """Fail at startup, naming every missing value at once."""
        required = {
            "POSTGRES_URL": self.postgres_url,
            "HEADSCALE_API_URL": self.headscale_api_url,
            "HEADSCALE_API_KEY": self.headscale_api_key,
            "HEADSCALE_PUBLIC_URL": self.headscale_public_url,
            "FACTORY_SECRET_V1": self.factory_secret_v1,
            "REDIS_URL": self.redis_url,
            "INTERNAL_SERVICE_SECRET": self.internal_service_secret,
        }
        if self.require_hmac_signature:
            required["HMAC_SECRET"] = self.hmac_secret
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError("Missing required configuration: " + ", ".join(missing))


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
