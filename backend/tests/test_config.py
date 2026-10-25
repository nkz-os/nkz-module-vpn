"""Settings: every secret the service cannot run without is checked at startup."""

import pytest

from app.config import Settings

REQUIRED = {
    "POSTGRES_URL": "postgresql://u:p@db:5432/nkz_vpn",
    "HEADSCALE_API_URL": "http://headscale:8080",
    "HEADSCALE_API_KEY": "hs-key",
    "HEADSCALE_PUBLIC_URL": "https://vpn.example.test",
    "FACTORY_SECRET_V1": "factory-secret",
    "REDIS_URL": "redis://redis:6379/0",
    "INTERNAL_SERVICE_SECRET": "internal",
    "HMAC_SECRET": "hmac",
}


@pytest.fixture
def clean_env(monkeypatch):
    for name in list(REQUIRED) + ["REQUIRE_HMAC_SIGNATURE", "CORS_ORIGINS"]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_validate_required_lists_all_missing(clean_env):
    with pytest.raises(RuntimeError) as exc:
        Settings(_env_file=None).validate_required()
    message = str(exc.value)
    for name in REQUIRED:
        assert name in message


def test_validate_required_passes_with_all_set(clean_env):
    for name, value in REQUIRED.items():
        clean_env.setenv(name, value)
    Settings(_env_file=None).validate_required()


def test_hmac_not_required_when_flag_false(clean_env):
    for name, value in REQUIRED.items():
        if name != "HMAC_SECRET":
            clean_env.setenv(name, value)
    clean_env.setenv("REQUIRE_HMAC_SIGNATURE", "false")
    Settings(_env_file=None).validate_required()


def test_hmac_required_by_default(clean_env):
    for name, value in REQUIRED.items():
        if name != "HMAC_SECRET":
            clean_env.setenv(name, value)
    with pytest.raises(RuntimeError, match="HMAC_SECRET"):
        Settings(_env_file=None).validate_required()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", []),
        ("https://a.example.test, https://b.example.test", ["https://a.example.test", "https://b.example.test"]),
        ('["https://a.example.test"]', ["https://a.example.test"]),
    ],
)
def test_cors_origins_accepts_csv_and_json(clean_env, raw, expected):
    clean_env.setenv("CORS_ORIGINS", raw)
    assert Settings(_env_file=None).cors_origin_list == expected


def test_claim_defaults_match_the_spec(clean_env):
    s = Settings(_env_file=None)
    assert s.preauth_ttl_minutes == 30
    assert (s.claim_limit_per_device, s.claim_limit_per_tenant) == (5, 5)
    assert s.claim_window_seconds == 3600
    assert s.api_prefix == "/api/vpn"
