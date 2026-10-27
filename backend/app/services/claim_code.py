"""
Claim codes for field devices.

    claim_code = "V{version}-" + first 8 chars of Base32(HMAC-SHA256(K_v, device_uuid))

The code is printed on the chassis at the factory and is the only proof of
possession the tenant presents when claiming the device. It is a pure
function of the device UUID and the versioned factory secret, so nothing is
stored: validation recomputes it and compares in constant time. A device
re-registered with the same UUID and version therefore keeps its printed code.

Rotation: if K_v1 leaks, set FACTORY_SECRET_V2 and FACTORY_SECRET_CURRENT_VERSION=2;
devices keep the version they were registered with (devices.claim_version). A
further version needs its own field in app.config.Settings.
"""

import base64
import hashlib
import hmac

CODE_BODY_LENGTH = 8  # 40 bits


def generate_claim_code(device_uuid: str, secret: str, version: int) -> str:
    mac = hmac.new(secret.encode("utf-8"), device_uuid.encode("utf-8"), hashlib.sha256).digest()
    body = base64.b32encode(mac).decode("ascii").rstrip("=")[:CODE_BODY_LENGTH]
    return f"V{version}-{body}"


_LOOKALIKES = str.maketrans({"0": "O", "1": "I", "8": "B"})  # Base32 bodies never contain 0, 1, 8 or 9


def normalize_claim_code(code: str) -> str:
    """Upper-case, drop all whitespace, and read 0/1/8 in the body as O/I/B (as typed from a label)."""
    compact = "".join(code.split()).upper()
    prefix, sep, body = compact.partition("-")
    return f"{prefix}{sep}{body.translate(_LOOKALIKES)}" if sep else compact


def validate_claim_code(device_uuid: str, submitted: str, secret: str, version: int) -> bool:
    expected = generate_claim_code(device_uuid, secret, version)
    return hmac.compare_digest(expected.encode("ascii"), normalize_claim_code(submitted).encode("utf-8"))


def factory_secret_for(settings, version: int) -> str:
    secret = getattr(settings, f"factory_secret_v{version}", "")
    if not secret:
        raise ValueError(f"factory secret version {version} not configured")
    return secret
