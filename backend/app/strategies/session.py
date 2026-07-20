from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class SessionTier(str, Enum):
    PRIME = "prime"  # London/NY overlap — best gold liquidity
    ALLOWED = "allowed"  # London morning or NY afternoon
    ASIA = "asia"  # Asia scalp desk window
    AVOID = "avoid"  # weekend / outside desk hours


@dataclass(frozen=True)
class SessionWindow:
    tier: SessionTier
    label: str
    reason: str


def _ph_hour(utc: datetime) -> int:
    """Philippines time = UTC+8."""
    return (utc.hour + 8) % 24


def classify_asia_desk(ts: datetime) -> SessionWindow:
    """Asia-first desk: scalp only PH 07:00–19:00 (UTC 23:00–11:00)."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    ph = _ph_hour(utc)
    # PH 7:00 inclusive → 19:00 exclusive
    if 7 <= ph < 19:
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia scalp desk (PH 7:00AM–7:00PM) — range / S/R scalping only",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "outside_asia_desk",
        "Outside Asia desk hours — next window PH 7:00AM–7:00PM",
    )


def classify_full_sessions(ts: datetime) -> SessionWindow:
    """Full gold session map (UTC) — London/NY + short Asia overnight."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    hour = utc.hour
    if 13 <= hour < 16:
        return SessionWindow(
            SessionTier.PRIME,
            "london_ny_overlap",
            "London/NY overlap — best XAUUSD liquidity",
        )
    if 7 <= hour < 13:
        return SessionWindow(
            SessionTier.ALLOWED,
            "london",
            "London session — good gold directional moves",
        )
    if 16 <= hour < 20:
        return SessionWindow(
            SessionTier.ALLOWED,
            "new_york",
            "New York session — USD-driven gold continuation",
        )
    if hour >= 23 or hour < 11:
        # Align with PH daytime Asia desk when full map is off
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia/Tokyo — range scalp window",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "off_hours",
        "Off-hours — spreads widen, skip new entries",
    )


def classify_session(ts: datetime) -> SessionWindow:
    """Active session map — Asia desk by default (JM_ASIA_DESK_ONLY)."""
    from app.core.config import get_settings

    if get_settings().asia_desk_only:
        return classify_asia_desk(ts)
    return classify_full_sessions(ts)


def session_allows_entry(ts: datetime, *, prime_only: bool = False) -> bool:
    tier = classify_session(ts).tier
    if prime_only:
        return tier == SessionTier.PRIME
    return tier in {SessionTier.PRIME, SessionTier.ALLOWED}


def session_allows_asia_scalp(ts: datetime) -> bool:
    return classify_session(ts).tier == SessionTier.ASIA
