"""
Device Management Backend - FastAPI Application

Zero-touch provisioning of field devices: factory registration, claim by the
tenant, Headscale pre-auth keys tagged for the field-device ACL, and the SDM
twin in Orion-LD.
"""

import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis_async
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.api.internal import router as internal_router
from app.config import Settings, get_settings
from app.db.session import Database
from app.deps import Services
from app.logging_setup import configure_logging
from app.services.headscale import HeadscaleClient
from app.services.pki import Pki
from app.services.ratelimit import ClaimLimiter
from app.services.twin import TwinWriter

logger = logging.getLogger(__name__)


async def build_services(settings: Settings) -> tuple[Services, list]:
    """Create every external client; return them with their close callbacks."""
    db = await Database.connect(settings.postgres_url)
    headscale = HeadscaleClient(settings.headscale_api_url, settings.headscale_api_key)
    redis_client = redis_async.from_url(settings.redis_url, password=settings.redis_password or None)
    services = Services(
        settings=settings,
        db=db,
        headscale=headscale,
        limiter=ClaimLimiter(redis_client, settings.claim_window_seconds),
        pki=Pki(settings.k8s_namespace, settings.iot_ca_issuer, settings.device_cert_duration),
        twin_writer=lambda tenant_id: TwinWriter(tenant_id),
    )
    return services, [db.close, headscale.close, redis_client.aclose]


def create_app(services: Services | None = None) -> FastAPI:
    """Application factory. Tests inject `services`; production builds them at startup."""
    settings = services.settings if services else get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        closers: list = []
        if services is None:
            settings.validate_required()  # fail fast: refuse to run half-configured
            app.state.services, closers = await build_services(settings)
        logger.info("%s v%s starting — prefix=%s", settings.app_name, settings.app_version, settings.api_prefix)
        try:
            yield
        finally:
            for close in closers:
                await close()
            logger.info("%s shutting down", settings.app_name)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Device Management - zero-touch provisioning for the Nekazari Platform",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )
    if services is not None:
        app.state.services = services

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    async def health_check():
        """Liveness/readiness probe."""
        return {"status": "healthy", "service": settings.app_name, "version": settings.app_version}

    app.include_router(api_router, prefix=settings.api_prefix)
    # Internal routes (robotics and other in-cluster callers) — authenticated
    # by X-Internal-Service-Secret, NOT gateway headers. See app/api/internal.py.
    app.include_router(internal_router, prefix=settings.api_prefix)
    return app


app = create_app()
