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


# Aug 19 Asia desk — PH 8:00AM–2:59PM (UTC 00:00–06:59)
ASIA_PH_START = 8
ASIA_PH_END = 15  # exclusive → until 3:00PM PH


def ph_hour(utc: datetime) -> int:
    """Philippines time = UTC+8."""
    return (utc.hour + 8) % 24


# Back-compat alias used by older imports
_ph_hour = ph_hour


def in_asia_ph_window(ph: int) -> bool:
    """PH 8:00AM–2:59PM — Aug 19 Asian session window."""
    return ASIA_PH_START <= ph < ASIA_PH_END


def classify_asia_desk(ts: datetime) -> SessionWindow:
    """Asia-only desk: EMA_RSI scalp PH 8AM–3PM; flat outside (JM_ASIA_DESK_ONLY)."""
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    ph = ph_hour(utc)
    if in_asia_ph_window(ph):
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia desk (PH 8:00AM–3:00PM) — EMA_RSI scalp",
        )
    return SessionWindow(
        SessionTier.AVOID,
        "outside_asia_desk",
        "Outside Asia desk hours — next window PH 8:00AM–3:00PM",
    )


def classify_full_sessions(ts: datetime) -> SessionWindow:
    """Full desk map aligned with Aug 19 strategy clocks (UTC).

    Asia 00:00–06:59 — EMA_RSI
    London 07:00–12:59 — EMA_RSI
    Overlap 13:00–17:59 — SMC
    New York 18:00–19:59 — EMA_VWAP
    Off-hours 20:00–22:59 — EMA_RSI (PH 4:00AM–6:59AM)
    """
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    hour = utc.hour

    if 0 <= hour < 7:
        return SessionWindow(
            SessionTier.ASIA,
            "asia",
            "Asia session (UTC 00:00–06:59) — EMA_RSI + Asia range box",
        )
    if 7 <= hour < 11:
        return SessionWindow(
            SessionTier.ALLOWED,
            "london",
            "London session (UTC 07:00–10:59) — EMA_RSI scalp",
        )
    if 11 <= hour < 12:
        return SessionWindow(
            SessionTier.ALLOWED,
            "london_wind_down",
            "London wind-down (UTC 11:00–11:59) — EMA_RSI scalp",
        )
    if 12 <= hour < 13:
        return SessionWindow(
            SessionTier.ALLOWED,
            "london_close",
            "London close (UTC 12:00–12:59) — EMA_RSI scalp",
        )
    if 13 <= hour < 18:
        return SessionWindow(
            SessionTier.PRIME,
            "london_ny_overlap",
            "London/NY overlap — best XAUUSD liquidity (SMC window)",
        )
    if 18 <= hour < 20:
        return SessionWindow(
            SessionTier.ALLOWED,
            "new_york",
            "New York session — USD-driven gold continuation",
        )
    return SessionWindow(
        SessionTier.ALLOWED,
        "off_hours",
        "Early Asia pre-open (UTC 20:00–22:59 / PH 4:00AM–6:59AM) — EMA_RSI scalp",
    )


def classify_session(ts: datetime) -> SessionWindow:
    """Active session map — Asia-only desk by default; full Aug 19 map if hybrid off."""
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
    """What comes after the current slot — strategy recommendation for planning.

    Looks up to 72h ahead so Friday night / weekend still arms Monday Asia.
    """
    utc = ts.astimezone(timezone.utc)
    current = classify_session(utc)
    for add in range(1, 73):
        probe = utc + timedelta(hours=add)
        nxt = classify_session(probe)
        if nxt.label != current.label and nxt.tier != SessionTier.AVOID:
            return {
                "from_session": current.label,
                "session": nxt.label,
                "tier": nxt.tier.value,
                "hour_utc": probe.hour,
                "strategy": _recommended_for_label(nxt.label, probe.hour),
                "reason": _recommend_reason(nxt.label),
            }
    return {
        "from_session": current.label,
        "session": None,
        "tier": "avoid",
        "strategy": "AI_ML",
        "reason": "No nearer session — keep AI_ML armed",
    }


_SESSION_STRATEGY = {
    "asia": "AI_ML",
    "london": "AI_ML",
    "london_wind_down": "AI_ML",
    "london_close": "AI_ML",
    "london_ny_overlap": "AI_ML",
    "new_york": "AI_ML",
    "off_hours": "AI_ML",
}

_SESSION_CHILD = {
    "asia": "EMA_RSI_Scalp",
    "london": "EMA_RSI_Scalp",
    "london_wind_down": "EMA_RSI_Scalp",
    "london_close": "EMA_RSI_Scalp",
    "london_ny_overlap": "Liquidity_Sweep_SMC",
    "new_york": "EMA_VWAP_Scalp",
    "off_hours": "EMA_RSI_Scalp",
}


def _recommended_for_label(label: str, hour_utc: int) -> str | None:
    return _SESSION_STRATEGY.get(label)


def _recommend_reason(label: str) -> str:
    pick = _SESSION_STRATEGY.get(label)
    child = _SESSION_CHILD.get(label)
    if pick and child:
        return f"Next slot {label} → {pick}/{child}"
    if pick:
        return f"Next slot {label} → {pick}"
    return f"Next slot {label} — stand aside"
