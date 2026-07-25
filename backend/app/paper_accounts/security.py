"""Password hashing for paper demo accounts (stdlib only)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 120_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return `pbkdf2$iterations$salt_hex$hash_hex`."""
    raw = (password or "").encode("utf-8")
    if len(raw) < 6:
        raise ValueError("Password must be at least 6 characters")
    if len(raw) > 128:
        raise ValueError("Password is too long")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not password:
        return False
    try:
        algo, iter_s, salt_hex, hash_hex = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2":
        return False
    try:
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(digest, expected)
