"""Keyed hashing and deterministic assignment (brief rules 8 and 15)."""
import hashlib
import hmac


def keyed_hash(secret: bytes, value: str) -> str:
    """HMAC-SHA-256, first 32 hex chars (128 bits). Raw values are never written."""
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def hash_u(salt: str, key: str) -> float:
    """Deterministic uniform [0,1) from a salted hash (holdout assignment)."""
    h = hashlib.sha256(f"{salt}:{key}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64
