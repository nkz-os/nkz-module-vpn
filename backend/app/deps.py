"""Service container and FastAPI dependency providers."""

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from app.config import Settings
from app.db.session import Database
from app.services.headscale import HeadscaleClient
from app.services.pki import Pki
from app.services.ratelimit import ClaimLimiter
from app.services.twin import TwinWriter


@dataclass
class Services:
    settings: Settings
    db: Database
    headscale: HeadscaleClient
    limiter: ClaimLimiter
    pki: Pki
    twin_writer: Callable[[str], TwinWriter]  # tenant_id -> writer (caller closes it)


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_client_ip(request: Request) -> str | None:
    """First hop of X-Forwarded-For (Traefik -> gateway preserve it), else the peer."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else None
