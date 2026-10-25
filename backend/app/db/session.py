"""
Connection pool and RLS-scoped transactions.

Every query runs inside a transaction that first sets app.current_tenant_id
(transaction-local). The tables FORCE row-level security, so a connection that
skips this sees no rows at all.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

PLATFORM_SCOPE = "__platform__"


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


class Database:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str, *, min_size: int = 1, max_size: int = 5) -> "Database":
        pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size, init=_init_connection)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def _scoped_tx(self, scope: str) -> AsyncIterator[asyncpg.Connection]:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant_id', $1, true)", scope)
            yield conn

    def tenant_tx(self, tenant_id: str):
        if not tenant_id or tenant_id == PLATFORM_SCOPE:
            raise ValueError("invalid tenant scope")
        return self._scoped_tx(tenant_id)

    def platform_tx(self):
        return self._scoped_tx(PLATFORM_SCOPE)

    @asynccontextmanager
    async def raw(self) -> AsyncIterator[asyncpg.Connection]:
        """Unscoped connection (maintenance and health checks only: RLS hides all rows)."""
        async with self._pool.acquire() as conn:
            yield conn
