"""User-facing API routes (behind the api-gateway)."""

from fastapi import APIRouter

from app.api.factory import router as factory_router

router = APIRouter()
router.include_router(factory_router)
