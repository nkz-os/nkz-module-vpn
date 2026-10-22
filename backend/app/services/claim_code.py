"""
Generación y validación de Claim Codes para dispositivos IoT.

Algoritmo:
    Claim_Code = "V{version}-" + Truncate(Base32(HMAC-SHA256(K_vN, UUID)), 8)
    Ejemplo: V1-NKZ8492X

Propiedades de seguridad:
    - One-time-use: el código se marca CONSUMED en BD tras el primer uso exitoso.
    - Sin caducidad temporal: los dispositivos pueden estar en almacén años.
    - Rate limiting: máximo 5 intentos fallidos por UUID en ventana de 1 hora.
    - Timing-safe: comparación con hmac.compare_digest para evitar timing attacks.
    - El Factory Secret nunca se expone en logs ni en respuestas API.

Rotación de Factory Secret:
    Si se compromete K_v1, crear K_v2 en el Secret de K8s y actualizar
    FACTORY_SECRET_CURRENT_VERSION=2. Los dispositivos fabricados antes siguen
    usando V1 (su claim_version se guarda en la BD).
"""

import hmac
import hashlib
import base64


def generate_claim_code(device_uuid: str, factory_secret: str, version: int) -> str:
    """
    Genera el Claim Code para imprimir en el chasis del dispositivo.
    Solo se llama desde el factory tool — nunca desde un endpoint público.
    """
    mac = hmac.new(
        factory_secret.encode("utf-8"),
        device_uuid.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    # Base32 sin padding, 8 caracteres = 40 bits de entropía
    code_body = base64.b32encode(mac).decode("ascii").rstrip("=")[:8]
    return f"V{version}-{code_body}"


def generate_claim_hash(device_uuid: str, factory_secret: str, version: int) -> str:
    """
    Genera el hash del Claim Code para almacenar en BD.
    Se almacena el hash del código completo (incluido el prefijo V{n}-).
    Así, comparar en validate_claim_code es una operación de string completo.
    """
    code = generate_claim_code(device_uuid, factory_secret, version)
    # Segundo hash SHA-256 sobre el código para lo que se almacena en BD
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def validate_claim_code(
    device_uuid: str,
    submitted_code: str,
    stored_hash: str,
    factory_secret: str,
    version: int,
) -> bool:
    """
    Valida que el código introducido por el usuario corresponde al dispositivo.

    No se recalcula el HMAC desde cero para validar: se hashea el código
    recibido y se compara con el stored_hash. Esto permite validar sin
    exponer el Factory Secret al flujo de comparación.
    """
    submitted_normalized = submitted_code.strip().upper()
    submitted_hash = hashlib.sha256(submitted_normalized.encode("utf-8")).hexdigest()
    # hmac.compare_digest es timing-safe (protege contra timing attacks)
    return hmac.compare_digest(submitted_hash, stored_hash)


def get_factory_secret_for_version(version: int, settings) -> str:
    """
    Devuelve el Factory Secret correspondiente a la versión indicada.
    Falla explícitamente si la versión no existe.
    """
    secret_attr = f"FACTORY_SECRET_V{version}"
    secret = getattr(settings, secret_attr, None)
    if not secret:
        raise ValueError(f"Factory secret version {version} not configured")
    return secret
