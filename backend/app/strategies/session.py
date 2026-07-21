from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class SessionTier(str, Enum):
    PRIME = "prime"  # London/NY overlap — best gold liquidity
    ALLOWED = "allowed"  # London afternoon or NY session
    ASIA = "asia"  # Asia scalp window (PH daytime)
    AVOID = "avoid"  # weekend / thin off-hours


@dataclass(frozen=True)
class SessionWindow:
    tier: SessionTier
    label: str
    reason: str


# Asia M3/M5 scalp desk — Philippines local hours
ASIA_PH_START = 7
ASIA_PH_END = 17  # exclusive → until 5:00PM


def ph_hour(utc: datetime) -> int:
    """Philippines time = UTC+8."""
    return (utc.hour + 8) % 24


# Back-compat alias used by older imports
_ph_hour = ph_hour


def classify_asia_desk(ts: datetime) -> SessionWindow:
    """Asia-only desk: scalp PH 07:00–17:00; flat outside (JM_ASIA_DESK_ONLY)."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    ph = ph_hour(utc)
    if ASIA_PH_START <= ph < ASIA_PH_END:
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia scalp desk (PH 7:00AM–5:00PM) — M5 Support/Resistance",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "outside_asia_desk",
        "Outside Asia desk hours — next window PH 7:00AM–5:00PM",
    )


def classify_full_sessions(ts: datetime) -> SessionWindow:
    """Full desk map: Asia PH 7AM–5PM, then London → Overlap → NY.

    Asia owns UTC 23:00–09:00 (PH 7AM–5PM).
    After PH 5PM (UTC 09:00) strategies restore to London/NY tools.
    """
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    hour = utc.hour
    ph = ph_hour(utc)

    if ASIA_PH_START <= ph < ASIA_PH_END:
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia session (PH 7:00AM–5:00PM) — M5 S/R scalping",
        )

    # After Asia close → London → overlap → NY
    if 9 <= hour < 13:
        return SessionWindow(
            SessionTier.ALLOWED,
            "london",
            "London after Asia — directional gold moves",
        )
    if 13 <= hour < 16:
        return SessionWindow(
            SessionTier.PRIME,
            "london_ny_overlap",
            "London/NY overlap — best XAUUSD liquidity",
        )
    if 16 <= hour < 20:
        return SessionWindow(
            SessionTier.ALLOWED,
            "new_york",
            "New York session — USD-driven gold continuation",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "off_hours",
        "Off-hours — spreads widen, skip new entries",
    )


def classify_session(ts: datetime) -> SessionWindow:
    """Active session map — full hybrid by default; Asia-only if configured."""
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


def next_session_hint(ts: datetime) -> dict:
    """What comes after the current slot — strategy recommendation for planning."""
    utc = ts.astimezone(timezone.utc)
    current = classify_session(utc)
    for add in range(1, 25):
        probe_hour = (utc.hour + add) % 24
        probe = utc + timedelta(hours=add)
        nxt = classify_session(probe)
        if nxt.label != current.label and nxt.tier != SessionTier.AVOID:
            return {
                "from_session": current.label,
                "session": nxt.label,
                "tier": nxt.tier.value,
                "hour_utc": probe_hour,
                "strategy": _recommended_for_label(nxt.label, probe_hour),
                "reason": _recommend_reason(nxt.label),
            }
        if nxt.label != current.label and nxt.tier == SessionTier.AVOID:
            continue
    return {
        "from_session": current.label,
        "session": None,
        "tier": "avoid",
        "strategy": None,
        "reason": "No tradeable session in the next 24h",
    }


def _recommended_for_label(label: str, hour_utc: int) -> str | None:
    return None


def _recommend_reason(label: str) -> str:
    return "Clean slate — no strategy assigned yet"
