"""User-facing API routes (behind the api-gateway)."""

from fastapi import APIRouter

from app.api.devices import router as devices_router
from app.api.factory import router as factory_router

router = APIRouter()
router.include_router(factory_router)
router.include_router(devices_router)
