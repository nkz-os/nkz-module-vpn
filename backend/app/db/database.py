"""
Configuración de base de datos con SQLAlchemy async.
"""

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.models import Base

engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    pool_size=5,
    max_overflow=10,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Crea las tablas si no existen. Se llama en el startup de la app."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db(request: Request):
    """Dependency de FastAPI para inyectar sesión de BD con tenant context."""
    async with AsyncSessionLocal() as session:
        tenant_id = getattr(request.state, 'tenant_id', None) if request else None
        # tenant_id is sanitized by normalize_tenant_id() → only [a-z0-9_].
        safe_id = tenant_id or ""
        await session.execute(
            text(f"SET LOCAL app.current_tenant_id = '{safe_id}'")
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
