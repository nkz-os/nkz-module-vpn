"""Claim codes: deterministic per device, validated by recomputation (nothing stored)."""

import base64
import hashlib
import hmac

import pytest

from app.config import Settings
from app.services.claim_code import (
    factory_secret_for,
    generate_claim_code,
    normalize_claim_code,
    validate_claim_code,
)

UUID_A = "3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c"
UUID_B = "8a7b6c5d-4e3f-4a2b-9c1d-0e1f2a3b4c5d"
SECRET = "factory-secret"


def reference_code(device_uuid: str, secret: str, version: int) -> str:
    mac = hmac.new(secret.encode(), device_uuid.encode(), hashlib.sha256).digest()
    return f"V{version}-" + base64.b32encode(mac).decode().rstrip("=")[:8]


def test_generate_matches_reference():
    # Same algorithm as the codes already printed on chassis: they must keep working.
    assert generate_claim_code(UUID_A, SECRET, 1) == reference_code(UUID_A, SECRET, 1)


def test_generate_is_deterministic():
    assert generate_claim_code(UUID_A, SECRET, 1) == generate_claim_code(UUID_A, SECRET, 1)
    assert generate_claim_code(UUID_A, SECRET, 1) != generate_claim_code(UUID_B, SECRET, 1)


def test_normalize_strips_and_uppercases():
    assert normalize_claim_code("  v1-abcd2345 \n") == "V1-ABCD2345"


def test_validate_normalizes():
    code = generate_claim_code(UUID_A, SECRET, 1)
    assert validate_claim_code(UUID_A, " " + code.lower() + " ", SECRET, 1)


def test_validate_rejects_other_device():
    code_for_a = generate_claim_code(UUID_A, SECRET, 1)
    assert not validate_claim_code(UUID_B, code_for_a, SECRET, 1)


def test_validate_rejects_wrong_version():
    code_v1 = generate_claim_code(UUID_A, SECRET, 1)
    assert not validate_claim_code(UUID_A, code_v1, SECRET, 2)


def test_validate_rejects_empty_and_garbage():
    assert not validate_claim_code(UUID_A, "", SECRET, 1)
    assert not validate_claim_code(UUID_A, "V1-", SECRET, 1)


def test_factory_secret_for_known_version():
    s = Settings(_env_file=None, factory_secret_v1="k1")
    assert factory_secret_for(s, 1) == "k1"


def test_factory_secret_for_unknown_version_raises():
    s = Settings(_env_file=None, factory_secret_v1="k1")
    with pytest.raises(ValueError, match="version 2 not configured"):
        factory_secret_for(s, 2)


def test_factory_secret_for_empty_secret_raises():
    s = Settings(_env_file=None, factory_secret_v1="")
    with pytest.raises(ValueError, match="version 1 not configured"):
        factory_secret_for(s, 1)
