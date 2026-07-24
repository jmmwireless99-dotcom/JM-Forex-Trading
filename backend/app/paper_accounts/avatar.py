"""Avatar / logo helpers for paper account profiles."""

from __future__ import annotations

_MAX_AVATAR_CHARS = 120_000  # ~90KB binary as data-URL
_ALLOWED_PREFIXES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/jpg;base64,",
    "data:image/webp;base64,",
)


def normalize_avatar(value: str | None) -> str | None:
    """Validate optional logo data-URL. Empty clears the avatar."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return ""
    lower = text.lower()
    if not any(lower.startswith(p) for p in _ALLOWED_PREFIXES):
        raise ValueError("Logo must be a PNG, JPEG, or WebP data URL")
    if len(text) > _MAX_AVATAR_CHARS:
        raise ValueError("Logo is too large (max ~90KB)")
    return text
