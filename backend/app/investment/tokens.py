"""Signed session tokens for investment auth."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings


def _secret() -> bytes:
    settings = get_settings()
    raw = getattr(settings, "invest_secret", None) or "jm-fx-invest-dev-secret-change-me"
    return raw.encode("utf-8")


def create_token(payload: dict[str, Any], *, ttl_seconds: int = 60 * 60 * 24 * 14) -> str:
    body = {
        **payload,
        "exp": int(time.time()) + ttl_seconds,
    }
    data = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
    sig = hmac.new(_secret(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        data, sig = token.rsplit(".", 1)
        expected = hmac.new(_secret(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(data.encode()))
        if int(payload.get("exp") or 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
