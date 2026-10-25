"""Shared fixtures.

Database tests run against a real PostgreSQL (RLS cannot be mocked). Set
TEST_POSTGRES_URL to a superuser DSN; the fixtures create a dedicated
non-superuser role that owns a throwaway database — the same shape as
production, where the module role owns nkz_vpn and FORCE RLS applies to it.
"""

import asyncio
import datetime as _dt
import os
from urllib.parse import urlparse, urlunparse

import asyncpg
import fakeredis
import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

TEST_ROLE = "nkz_module_vpn_test"
TEST_ROLE_PASSWORD = "test"
TEST_DB = "nkz_vpn_test"


def _admin_dsn() -> str | None:
    return os.environ.get("TEST_POSTGRES_URL")


def _module_dsn(admin_dsn: str) -> str:
    u = urlparse(admin_dsn)
    netloc = f"{TEST_ROLE}:{TEST_ROLE_PASSWORD}@{u.hostname}:{u.port or 5432}"
    return urlunparse(u._replace(netloc=netloc, path=f"/{TEST_DB}"))


async def _recreate_database(admin_dsn: str) -> None:
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", TEST_ROLE)
        if not exists:
            await conn.execute(
                f"CREATE ROLE {TEST_ROLE} LOGIN PASSWORD '{TEST_ROLE_PASSWORD}' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        await conn.execute(f"CREATE DATABASE {TEST_DB} OWNER {TEST_ROLE}")
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """Module-role DSN of a freshly created, migrated database."""
    admin = _admin_dsn()
    if not admin:
        pytest.skip("TEST_POSTGRES_URL not set: database tests need a real PostgreSQL")
    from app.db.migrate import run_migrations

    asyncio.run(_recreate_database(admin))
    dsn = _module_dsn(admin)
    asyncio.run(run_migrations(dsn))
    return dsn


@pytest.fixture
async def db(pg_dsn):
    """A connected Database on empty tables."""
    from app.db.session import Database

    database = await Database.connect(pg_dsn)
    async with database.raw() as conn:
        await conn.execute("TRUNCATE devices, device_events RESTART IDENTITY")
    try:
        yield database
    finally:
        await database.close()


# --------------------------------------------------------------------------
# Application fixtures: the app with injected services (no lifespan), the
# gateway headers it trusts, and stubs for the parts that need a cluster.
# --------------------------------------------------------------------------

HEADSCALE_URL = "http://headscale.test:8080"
ORION_URL = "http://orion.test:1026"
CONTEXT_URL = "http://ctx.test/context.json"
FACTORY_SECRET = "factory-secret"


def gateway_headers(tenant: str = "acme", roles: str = "TenantAdmin", user: str = "u1") -> dict[str, str]:
    return {"X-Tenant-ID": tenant, "X-User-ID": user, "X-User-Roles": roles}


def make_csr(common_name: str, org_unit: str) -> tuple[str, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nekazari"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, org_unit),
        ]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode(), key


def self_signed_pem(common_name: str) -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = _dt.datetime.now(_dt.UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now)
        .not_valid_after(now + _dt.timedelta(days=1)).sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


class StubPki:
    """Stands in for cert-manager: signs nothing, returns fixed PEMs."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.ca_pem = self_signed_pem("test-iot-ca")

    async def sign_csr(self, csr_pem: str, device_uuid: str, device_type: str):
        from app.services.pki import SignedCertificate

        self.calls.append((device_uuid, device_type))
        return SignedCertificate(certificate_pem=self_signed_pem(device_uuid), ca_pem=self.ca_pem)


@pytest.fixture(autouse=True)
def _gateway_signature_off(monkeypatch):
    """The SDK reads REQUIRE_HMAC_SIGNATURE at import; tests opt in explicitly."""
    import nkz_platform_sdk.auth as sdk_auth

    monkeypatch.setattr(sdk_auth, "REQUIRE_HMAC", False)
    monkeypatch.setattr(sdk_auth, "HMAC_SECRET", "")


@pytest.fixture
def settings():
    from app.config import Settings

    return Settings(
        _env_file=None,
        headscale_api_url=HEADSCALE_URL,
        headscale_public_url="https://vpn.example.test",
        headscale_api_key="hs-key",
        factory_secret_v1=FACTORY_SECRET,
        internal_service_secret="internal-secret",
        hmac_secret="hmac-secret",
    )


@pytest.fixture
async def services(db, settings):
    from nkz_platform_sdk import OrionClient

    from app.deps import Services
    from app.services.headscale import HeadscaleClient
    from app.services.ratelimit import ClaimLimiter
    from app.services.twin import TwinWriter

    headscale = HeadscaleClient(HEADSCALE_URL, "hs-key")
    svc = Services(
        settings=settings,
        db=db,
        headscale=headscale,
        limiter=ClaimLimiter(fakeredis.FakeAsyncRedis(), settings.claim_window_seconds),
        pki=StubPki(),
        twin_writer=lambda tenant: TwinWriter(
            tenant, orion=OrionClient(tenant, base_url=ORION_URL, context_url=CONTEXT_URL)),
    )
    try:
        yield svc
    finally:
        await headscale.close()


@pytest.fixture
async def api(services):
    from app.main import create_app

    app = create_app(services=services)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://vpn.test") as client:
        yield client
