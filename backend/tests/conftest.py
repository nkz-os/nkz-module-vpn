"""Shared fixtures.

Database tests run against a real PostgreSQL (RLS cannot be mocked). Set
TEST_POSTGRES_URL to a superuser DSN; the fixtures create a dedicated
non-superuser role that owns a throwaway database — the same shape as
production, where the module role owns nkz_vpn and FORCE RLS applies to it.
"""

import asyncio
import os
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest

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
