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
    """Client address for the audit trail: first hop of X-Forwarded-For, else unknown.

    Never the TCP peer: behind the api-gateway that is the gateway's own address.
    Audit only — it is client-controlled and never used for limits.
    """
    first = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return first or None
