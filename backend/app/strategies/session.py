from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class SessionTier(str, Enum):
    PRIME = "prime"  # London/NY overlap — best gold liquidity
    ALLOWED = "allowed"  # London morning or NY afternoon
    AVOID = "avoid"  # Asia / dead zones / weekend


@dataclass(frozen=True)
class SessionWindow:
    tier: SessionTier
    label: str
    reason: str


def classify_session(ts: datetime) -> SessionWindow:
    """Gold session map (UTC).

    - PRIME: 13:00–16:00 overlap (highest quality)
    - ALLOWED: 07:00–13:00 London, 16:00–20:00 NY continuation
    - AVOID: everything else + weekend
    """
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:  # Saturday=5, Sunday=6
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
    return SessionWindow(
        SessionTier.AVOID,
        "asia_off",
        "Asia/off-hours — spreads widen, fake breaks common",
    )


def session_allows_entry(ts: datetime, *, prime_only: bool = False) -> bool:
    tier = classify_session(ts).tier
    if prime_only:
        return tier == SessionTier.PRIME
    return tier in {SessionTier.PRIME, SessionTier.ALLOWED}
