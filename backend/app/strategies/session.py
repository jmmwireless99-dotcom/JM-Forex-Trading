from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class SessionTier(str, Enum):
    PRIME = "prime"  # London/NY overlap — best gold liquidity
    ALLOWED = "allowed"  # London afternoon or NY session
    ASIA = "asia"  # Asia scalp window (PH daytime)
    AVOID = "avoid"  # weekend / thin off-hours / kill windows


@dataclass(frozen=True)
class SessionWindow:
    tier: SessionTier
    label: str
    reason: str


@dataclass(frozen=True)
class SessionSlot:
    """One Mon–Fri desk slot: UTC hour window → strategy (or stand aside)."""

    label: str  # machine id: asia, london, ...
    slot: str  # UI name
    utc_start: int  # inclusive hour 0–23
    utc_end: int  # exclusive hour 1–24
    strategy: str | None
    tier: SessionTier
    reason: str

    @property
    def utc_range(self) -> str:
        end_h = self.utc_end - 1
        return f"{self.utc_start:02d}:00-{end_h:02d}:59"

    @property
    def ph_range(self) -> str:
        """Philippines = UTC+8 display of the same window."""
        ph_start = (self.utc_start + 8) % 24
        ph_end_h = (self.utc_end - 1 + 8) % 24
        return f"{ph_start:02d}:00-{ph_end_h:02d}:59"


# Canonical Mon–Fri map — quality windows only (not every thin hour).
# Weekend + Friday late still stand aside. London kill still cancels Judas at 12:00 UTC.
FULL_SESSION_SLOTS: tuple[SessionSlot, ...] = (
    SessionSlot(
        label="asia",
        slot="Asia",
        utc_start=0,
        utc_end=7,
        strategy="EMA_RSI_Scalp",
        tier=SessionTier.ASIA,
        reason="Asia session (UTC 00:00–06:59 / PH 08:00–14:59) — EMA_RSI quality pullbacks",
    ),
    SessionSlot(
        label="london",
        slot="London",
        utc_start=7,
        utc_end=11,
        strategy="London_Judas_Sweep",
        tier=SessionTier.ALLOWED,
        reason="London Judas window (UTC 07:00–10:59 / PH 15:00–18:59) — sweep + FVG limit",
    ),
    SessionSlot(
        label="london_wind_down",
        slot="London wind-down",
        utc_start=11,
        utc_end=12,
        strategy=None,
        tier=SessionTier.AVOID,
        reason="London wind-down (UTC 11:00–11:59 / PH 19:00–19:59) — stand aside, Judas cools",
    ),
    SessionSlot(
        label="london_close",
        slot="London close",
        utc_start=12,
        utc_end=13,
        strategy=None,
        tier=SessionTier.AVOID,
        reason="London close (UTC 12:00–12:59 / PH 20:00–20:59) — kill Judas limits, no new entries",
    ),
    SessionSlot(
        label="london_ny_overlap",
        slot="London/NY overlap",
        utc_start=13,
        utc_end=16,
        strategy="Liquidity_Sweep_SMC",
        tier=SessionTier.PRIME,
        reason="London/NY overlap (UTC 13:00–15:59 / PH 21:00–23:59) — best XAUUSD liquidity",
    ),
    SessionSlot(
        label="new_york",
        slot="New York",
        utc_start=16,
        utc_end=20,
        strategy="EMA_RSI_Scalp",
        tier=SessionTier.ALLOWED,
        reason="New York session (UTC 16:00–19:59 / PH 00:00–03:59) — USD-driven gold continuation",
    ),
    SessionSlot(
        label="off_hours",
        slot="Off-hours",
        utc_start=20,
        utc_end=24,
        strategy=None,
        tier=SessionTier.AVOID,
        reason="Off-hours (UTC 20:00–23:59 / PH 04:00–07:59) — thin tape, stand aside",
    ),
)


# Friday late — no new entries into weekend gap (UTC ≥ 18:00 Fri)
FRIDAY_LATE_UTC_HOUR = 18


SESSION_STRATEGY = {
    slot.label: slot.strategy for slot in FULL_SESSION_SLOTS if slot.strategy
}


# Asia M3/M5 scalp desk — Philippines local hours (JM_ASIA_DESK_ONLY)
ASIA_PH_START = 7
ASIA_PH_END = 17  # exclusive → until 5:00PM


def ph_hour(utc: datetime) -> int:
    """Philippines time = UTC+8."""
    return (utc.hour + 8) % 24


# Back-compat alias used by older imports
_ph_hour = ph_hour


def _slot_for_hour(hour: int) -> SessionSlot:
    for slot in FULL_SESSION_SLOTS:
        if slot.utc_start <= hour < slot.utc_end:
            return slot
    return FULL_SESSION_SLOTS[-1]


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
    """Full desk map — quality Mon–Fri windows only.

    Asia 00:00–06:59 — EMA_RSI
    London 07:00–10:59 — Judas sweep/entry
    London wind-down 11:00–11:59 — stand aside
    London close 12:00–12:59 — kill Judas limits + stand aside
    Overlap 13:00–15:59 — SMC
    New York 16:00–17:59 Fri / 16:00–19:59 Mon–Thu — EMA_RSI
    Off-hours 20:00–23:59 — stand aside (thin)
    Friday ≥ 18:00 UTC — friday_late stand aside (weekend gap)
    Weekend — stand aside
    Auto-transfer re-applies this map every UTC hour.
    """
    utc = ts.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return SessionWindow(SessionTier.AVOID, "weekend", "Gold market closed / thin weekend tape")

    if utc.weekday() == 4 and utc.hour >= FRIDAY_LATE_UTC_HOUR:
        return SessionWindow(
            SessionTier.AVOID,
            "friday_late",
            "Friday late (UTC ≥ 18:00) — stand aside before weekend gap",
        )

    slot = _slot_for_hour(utc.hour)
    return SessionWindow(slot.tier, slot.label, slot.reason)


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


def schedule_table() -> list[dict]:
    """UI / API schedule rows — strategy + UTC + PH + hourly auto-transfer note."""
    rows = [
        {
            "days": "Mon-Fri",
            "utc": slot.utc_range,
            "ph": slot.ph_range,
            "slot": slot.slot,
            "session": slot.label,
            "strategies": slot.strategy or "Stand aside",
        }
        for slot in FULL_SESSION_SLOTS
    ]
    rows.append(
        {
            "days": "Fri",
            "utc": f"{FRIDAY_LATE_UTC_HOUR:02d}:00-23:59",
            "ph": f"{(FRIDAY_LATE_UTC_HOUR + 8) % 24:02d}:00-07:59",
            "slot": "Friday late",
            "session": "friday_late",
            "strategies": "Stand aside (weekend gap protect)",
        }
    )
    rows.append(
        {
            "days": "Mon-Fri",
            "utc": "every hour (:00)",
            "ph": "every hour (:00 PH+8)",
            "slot": "Auto transfer",
            "session": "hourly",
            "strategies": "Quality windows — re-check time session each UTC hour",
        }
    )
    rows.append(
        {
            "days": "Sat-Sun",
            "utc": "all day",
            "ph": "all day",
            "slot": "Weekend",
            "session": "weekend",
            "strategies": "Stand aside (market closed)",
        }
    )
    return rows


def _recommended_for_label(label: str, hour_utc: int) -> str | None:
    return SESSION_STRATEGY.get(label)


def _recommend_reason(label: str) -> str:
    pick = SESSION_STRATEGY.get(label)
    if pick:
        return f"Next slot {label} → {pick}"
    return f"Next slot {label} — stand aside"


# Back-compat alias
_SESSION_STRATEGY = SESSION_STRATEGY
