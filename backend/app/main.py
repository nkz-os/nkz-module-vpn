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
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db
from app.routes import devices, factory, peers

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from app.config import settings as _s
ALLOWED_ORIGINS = [o.strip() for o in _s.CORS_ORIGINS.split(",") if o.strip()]


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
)

app.include_router(devices.router, prefix="/api/vpn")
app.include_router(factory.router, prefix="/api/vpn")
app.include_router(peers.router, prefix="/api/vpn")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "nkz-network-controller", "version": "1.0.0"}
