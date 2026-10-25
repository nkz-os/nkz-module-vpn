"""Process-level behaviour: refuse to start half-configured; migration entrypoint."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import migrate
from app.main import create_app

REQUIRED = ["POSTGRES_URL", "HEADSCALE_API_URL", "HEADSCALE_API_KEY", "HEADSCALE_PUBLIC_URL",
            "FACTORY_SECRET_V1", "REDIS_URL", "INTERNAL_SERVICE_SECRET", "HMAC_SECRET"]


@pytest.fixture
def bare_env(monkeypatch):
    for name in REQUIRED + ["REQUIRE_HMAC_SIGNATURE"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir("/")  # no stray .env
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_startup_fails_without_required_config(bare_env):
    app = create_app()
    with pytest.raises(RuntimeError, match="POSTGRES_URL"), TestClient(app):
        pass


def test_startup_fails_without_hmac_secret(bare_env):
    for name in REQUIRED:
        if name != "HMAC_SECRET":
            bare_env.setenv(name, "x")
    app = create_app()
    with pytest.raises(RuntimeError, match="HMAC_SECRET"), TestClient(app):
        pass


def test_migrate_main_without_dsn_exits_1(bare_env):
    assert migrate.main() == 1


async def test_openapi_lists_all_routes(api):
    paths = (await api.get("/api/vpn/openapi.json")).json()["paths"]
    for path in ["/api/vpn/devices", "/api/vpn/devices/claim", "/api/vpn/devices/validate",
                 "/api/vpn/devices/{device_uuid}", "/api/vpn/devices/{device_uuid}/events",
                 "/api/vpn/factory/register-device", "/api/vpn/factory/sign-csr",
                 "/api/vpn/internal/devices/{device_uuid}"]:
        assert path in paths, path


def test_client_ip_only_from_forwarded_header():
    from starlette.requests import Request

    from app.deps import get_client_ip

    def req(headers):
        return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                        "client": ("10.0.0.5", 1234)})

    assert get_client_ip(req({})) is None  # never the proxy's own address
    assert get_client_ip(req({"X-Forwarded-For": "203.0.113.7, 10.0.0.9"})) == "203.0.113.7"


def test_redis_client_has_timeouts():
    from app.config import Settings
    from app.main import redis_client_for

    client = redis_client_for(Settings(_env_file=None, redis_url="redis://127.0.0.1:6379/0"))
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] and kwargs["socket_connect_timeout"]
