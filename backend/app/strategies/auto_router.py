"""Session-based strategy router for XAUUSD scalp desk."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum

from app.strategies.session import SessionTier, classify_session, next_session_hint


class Regime(str, Enum):
    TREND = "trend"
    PULLBACK = "pullback"
    RANGE = "range"
    VOLATILE = "volatile"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AutoDecision:
    allow_trading: bool
    strategy: str | None
    regime: Regime
    slot: str
    day: str
    weekday: int
    hour_utc: int
    session_tier: str
    reason: str
    adx: float | None = None
    atr: float | None = None
    child_strategy: str | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        data["regime"] = self.regime.value
        return data


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Classic child under the AI_ML umbrella (session → setup engine)
_CHILD_BY_SESSION = {
    "asia": "EMA_RSI_Scalp",
    "london": "EMA_RSI_Scalp",
    "london_wind_down": "EMA_RSI_Scalp",
    "london_close": "EMA_RSI_Scalp",
    "london_ny_overlap": "Liquidity_Sweep_SMC",
    "new_york": "EMA_VWAP_Scalp",
    "off_hours": "EMA_RSI_Scalp",
}


class AutoStrategyRouter:
    """Maps session slots to AI_ML (Machine Learning stack) + child setup."""

    name = "auto_gold"

    def __init__(self, *, news_filter: bool = True, **_: object) -> None:
        self.news_filter = news_filter
        self.last_decision: AutoDecision | None = None
        # Auto-follow always parks on AI_ML when the session is tradeable.
        self.session_map: dict[str, str | None] = {
            "asia": "AI_ML",
            "london": "AI_ML",
            "london_close": "AI_ML",
            "london_wind_down": "AI_ML",
            "london_ny_overlap": "AI_ML",
            "new_york": "AI_ML",
            "off_hours": "AI_ML",
            "friday_late": None,
            "weekend": None,
            "outside_asia_desk": None,
        }
        self.child_map = dict(_CHILD_BY_SESSION)

    def _pick(self, session_label: str) -> str | None:
        return self.session_map.get(session_label)

    def _child(self, session_label: str) -> str | None:
        return self.child_map.get(session_label)

    def decide(self, ts: datetime, prices: list[float]) -> AutoDecision:
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        day = DAY_NAMES[utc.weekday()]
        pick = self._pick(session.label)
        child = self._child(session.label)
        allow = session.tier != SessionTier.AVOID and pick is not None
        if allow:
            reason = f"Session {session.label}: AI_ML → {child}"
        else:
            reason = f"Session {session.label}: stand aside"
        decision = AutoDecision(
            allow,
            pick,
            Regime.RANGE if allow else Regime.BLOCKED,
            session.label,
            day,
            utc.weekday(),
            utc.hour,
            session.tier.value,
            reason,
            child_strategy=child,
        )
        self.last_decision = decision
        return decision

    def session_default(self, ts: datetime) -> dict:
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        nxt = next_session_hint(utc)
        child = self._child(session.label)
        return {
            "session": session.label,
            "tier": session.tier.value,
            "day": DAY_NAMES[utc.weekday()],
            "hour_utc": utc.hour,
            "strategy": self._pick(session.label),
            "child_strategy": child,
            "mode": "session_follow",
            "recommended": self._pick(session.label) is not None,
            "next_session": nxt,
            "reason": f"AI_ML session-follow for {session.label}"
            + (f" → {child}" if child else ""),
        }

    def recommend(self, ts: datetime, prices: list[float]) -> dict:
        base = self.session_default(ts)
        decision = self.decide(ts, prices)
        return {
            **base,
            "regime": decision.regime.value,
            "allow_trading": decision.allow_trading,
            "strategy": decision.strategy,
            "child_strategy": decision.child_strategy,
            "active_pick": decision.strategy,
            "stand_aside": not decision.allow_trading,
            "reason": decision.reason,
            "adx": decision.adx,
            "atr": decision.atr,
            "transfer_to": decision.strategy,
        }

    def schedule_table(self) -> list[dict]:
        return [
            {
                "days": "Mon-Fri",
                "utc": "23:00-12:59",
                "ph": "07:00-20:59",
                "slot": "Asia",
                "session": "asia",
                "strategies": "AI_ML → EMA_RSI_Scalp",
            },
            {
                "days": "Mon-Fri",
                "utc": "13:00-17:59",
                "ph": "21:00-01:59",
                "slot": "London/NY overlap",
                "session": "london_ny_overlap",
                "strategies": "AI_ML → Liquidity_Sweep_SMC",
            },
            {
                "days": "Mon-Fri",
                "utc": "18:00-19:59",
                "ph": "02:00-03:59",
                "slot": "New York",
                "session": "new_york",
                "strategies": "AI_ML → EMA_VWAP_Scalp",
            },
            {
                "days": "Mon-Fri",
                "utc": "20:00-22:59",
                "ph": "04:00-06:59",
                "slot": "Early Asia",
                "session": "off_hours",
                "strategies": "AI_ML → EMA_RSI_Scalp",
            },
        ]
