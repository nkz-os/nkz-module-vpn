"""
Middleware de autenticación JWT (RS256, Keycloak).
Idéntico al patrón del resto de servicios Nekazari.
"""

import logging
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
import os
from app.common.tenant_utils import normalize_tenant_id

from app.config import settings

logger = logging.getLogger(__name__)

_jwks_client: Optional[PyJWKClient] = None
security = HTTPBearer()

def get_jwks_url() -> str:
    return f"{settings.jwt_issuer_url}/protocol/openid-connect/certs"


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(get_jwks_url())
    return _jwks_client


async def verify_token(token: str) -> dict:
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        token_issuer = unverified.get("iss")

        # Fallo duro — nunca continuar con issuer incorrecto
        if token_issuer != settings.jwt_issuer_url:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer",
            )

        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.jwt_issuer_url,
            options={"verify_exp": True, "verify_iss": True},
        )
        return payload

    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    except Exception as e:
        logger.error(f"Token verification error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token verification failed")


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Dependency: requiere JWT válido. Devuelve el payload."""
    return await verify_token(credentials.credentials)


async def require_factory_role(
    payload: dict = Depends(require_auth),
) -> dict:
    """
    Dependency: requiere rol 'Factory' en el JWT.
    Solo los operarios de fábrica pueden firmar CSRs y registrar dispositivos.
    """
    roles = payload.get("realm_access", {}).get("roles", [])
    if "Factory" not in roles and "PlatformAdmin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Factory or PlatformAdmin role required",
        )
    return payload


def get_tenant_id(request: Request) -> str:
    """Extract and normalize tenant ID from request headers."""
    # SOTA: Support both headers, prioritizing Fiware-Service
    tenant_id = request.headers.get('Fiware-Service') or request.headers.get('X-Tenant-ID')
    
    if not tenant_id:
        logger.warning("Missing tenant ID header (Fiware-Service or X-Tenant-ID)")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID header is required (Fiware-Service or X-Tenant-ID)"
        )
    
    try:
        # SOTA: Always normalize tenant ID for consistency across the ecosystem
        return normalize_tenant_id(tenant_id)
    except ValueError as e:
        logger.error(f"Invalid tenant ID format: {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format"
        )
