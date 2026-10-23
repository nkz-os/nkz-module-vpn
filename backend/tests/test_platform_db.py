"""Factory registration is a platform operation: its session uses the RLS platform scope."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost:5432/x")
os.environ.setdefault("HEADSCALE_API_KEY", "dummy")
os.environ.setdefault("FACTORY_SECRET_V1", "dummy")

from app.db import database  # noqa: E402
from app.routes import factory  # noqa: E402


def _dependencies(endpoint):
    import inspect

    return [p.default.dependency for p in inspect.signature(endpoint).parameters.values()
            if hasattr(p.default, "dependency")]


def test_register_device_uses_the_platform_session():
    assert database.get_platform_db in _dependencies(factory.register_device)


@pytest.mark.asyncio
async def test_platform_session_sets_the_platform_scope():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    factory_cm = MagicMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=None)
    with patch.object(database, "AsyncSessionLocal", return_value=factory_cm):
        gen = database.get_platform_db()
        assert await gen.__anext__() is session
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    stmt, params = session.execute.call_args.args
    assert "app.current_tenant_id" in str(stmt)
    assert params == {"scope": "__platform__"}
    session.commit.assert_awaited_once()
