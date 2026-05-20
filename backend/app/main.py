"""
NKZ Network Controller — FastAPI application.

Responsabilidades:
    - Gestión del ciclo de vida de dispositivos IoT (claim codes, ZTP)
    - Integración con Headscale (plano de control SDN)
    - Firma de certificados X.509 via cert-manager
    - Endpoints de consulta de peers para el módulo connectivity

Este servicio es el ÚNICO autorizado a llamar a la API de Headscale.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db.database import init_db
from app.routes import devices, factory, peers
from app.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from app.config import settings as _s


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NKZ Network Controller...")
    _ = _s.jwt_issuer_url  # Force early evaluation — fail at startup if JWT issuer is unconfigured
    await init_db()
    logger.info("Database tables ready.")
    yield
    logger.info("Shutting down NKZ Network Controller.")


app = FastAPI(
    title="NKZ Network Controller",
    description="Device provisioning, SDN management and PKI for Nekazari IoT.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(devices.router, prefix="/api/vpn")
app.include_router(factory.router, prefix="/api/vpn")
app.include_router(peers.router, prefix="/api/vpn")


@app.get("/health")
@limiter.exempt
async def health():
    return {"status": "healthy", "service": "nkz-network-controller", "version": "1.0.0"}
