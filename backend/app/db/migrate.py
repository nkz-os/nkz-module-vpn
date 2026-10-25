"""
Schema migrations: numbered SQL files in backend/migrations, applied in name
order, each in its own transaction, recorded in schema_migrations. Idempotent
and safe against concurrent runs (advisory lock).

Run before the API starts (initContainer):  python -m app.db.migrate
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_LOCK_KEY = 0x766E_6D69  # arbitrary, stable: "vnmi"


async def run_migrations(dsn: str, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; return the versions applied by this call."""
    files = sorted(migrations_dir.glob("*.sql"))
    applied_now: list[str] = []
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", _LOCK_KEY)
        try:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
            for path in files:
                if path.name in done:
                    continue
                async with conn.transaction():
                    await conn.execute(path.read_text(encoding="utf-8"))
                    await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", path.name)
                logger.info("migration applied: %s", path.name)
                applied_now.append(path.name)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _LOCK_KEY)
    finally:
        await conn.close()
    return applied_now


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    dsn = os.environ.get("POSTGRES_URL", "")
    if not dsn:
        logger.error("POSTGRES_URL is not set")
        return 1
    try:
        applied = asyncio.run(run_migrations(dsn))
    except Exception as exc:  # report and fail the initContainer
        logger.error("migration failed: %s", exc)
        return 1
    logger.info("migrations up to date (%d applied now)", len(applied))
    return 0


if __name__ == "__main__":
    sys.exit(main())
