from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum

from app.strategies.indicators import adx, atr, ema
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session


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

    def as_dict(self) -> dict:
        data = asdict(self)
        data["regime"] = self.regime.value
        return data


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class AutoStrategyRouter:
    """Pick gold strategy automatically from day + session + market regime.

    Schedule (UTC):
      Mon–Fri 07–13  London     → confluence / ATR trend (range = flat)
      Mon–Fri 13–16  Overlap    → confluence (ATR trend if strong trend)
      Mon–Fri 16–18  NY         → ATR trend / confluence
      Mon–Fri 18–20  NY late    → confluence only if trend; else flat
      Fri 18+ / weekend / Asia  → no new trades
      News blackout / chop      → no new trades
    """

    name = "auto_gold"

    def __init__(
        self,
        *,
        news_filter: bool = True,
        min_trend_adx: float = 28.0,
        min_trade_adx: float = 20.0,
        high_atr: float = 1.8,
    ) -> None:
        self.news_filter = news_filter
        self.min_trend_adx = min_trend_adx
        self.min_trade_adx = min_trade_adx
        self.high_atr = high_atr
        self.last_decision: AutoDecision | None = None

    def detect_regime(self, prices: list[float]) -> tuple[Regime, float | None, float | None]:
        vol = atr(prices, 14)
        strength = adx(prices, 14)
        fast = ema(prices, 21)
        slow = ema(prices, 55)
        if vol is None or strength is None or fast is None or slow is None:
            return Regime.RANGE, strength, vol

        if vol >= self.high_atr and strength >= self.min_trend_adx:
            return Regime.VOLATILE, strength, vol
        if strength >= self.min_trend_adx and abs(fast - slow) > 0.15 * vol:
            return Regime.TREND, strength, vol
        if strength >= self.min_trade_adx:
            return Regime.PULLBACK, strength, vol
        return Regime.RANGE, strength, vol

    def decide(self, ts: datetime, prices: list[float]) -> AutoDecision:
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        day = DAY_NAMES[utc.weekday()]
        hour = utc.hour
        regime, adx_v, atr_v = self.detect_regime(prices)

        # Weekend / Asia hard block
        if session.tier == SessionTier.AVOID:
            decision = AutoDecision(
                False,
                None,
                Regime.BLOCKED,
                session.label,
                day,
                utc.weekday(),
                hour,
                session.tier.value,
                session.reason,
                adx_v,
                atr_v,
            )
            self.last_decision = decision
            return decision

        # Friday late — avoid weekend gap risk
        if utc.weekday() == 4 and hour >= 18:
            decision = AutoDecision(
                False,
                None,
                Regime.BLOCKED,
                "friday_late",
                day,
                utc.weekday(),
                hour,
                session.tier.value,
                "Friday after 18:00 UTC — no new gold trades (weekend gap risk)",
                adx_v,
                atr_v,
            )
            self.last_decision = decision
            return decision

        # News blackout
        if self.news_filter:
            news = check_news_blackout(utc)
            if news.blocked:
                decision = AutoDecision(
                    False,
                    None,
                    Regime.BLOCKED,
                    session.label,
                    day,
                    utc.weekday(),
                    hour,
                    session.tier.value,
                    news.reason,
                    adx_v,
                    atr_v,
                )
                self.last_decision = decision
                return decision

        strategy, reason = self._pick_strategy(session.label, session.tier, regime, hour)
        allow = strategy is not None
        decision = AutoDecision(
            allow,
            strategy,
            regime if allow else Regime.BLOCKED,
            session.label,
            day,
            utc.weekday(),
            hour,
            session.tier.value,
            reason,
            adx_v,
            atr_v,
        )
        self.last_decision = decision
        return decision

    def _pick_strategy(
        self,
        slot: str,
        tier: SessionTier,
        regime: Regime,
        hour: int,
    ) -> tuple[str | None, str]:
        # Chop / range → never force RSI fades (they bled paper PnL).
        if regime == Regime.RANGE:
            return None, f"{slot}: range/chop — stand aside (no mean-reversion)"

        if tier == SessionTier.PRIME:
            if regime in {Regime.TREND, Regime.VOLATILE}:
                return (
                    "gold_atr_trend",
                    "Overlap + strong trend — ATR trend strategy",
                )
            return (
                "gold_confluence",
                "Overlap pullback regime — confluence entries",
            )

        if slot == "london":
            if regime == Regime.TREND:
                return "gold_atr_trend", "London trend day — ATR trend"
            return "gold_confluence", "London session — confluence pullback"

        if slot == "new_york":
            if hour >= 18:
                if regime in {Regime.TREND, Regime.VOLATILE}:
                    return "gold_confluence", "Late NY — confluence only if trend continues"
                return None, "Late NY without trend — stand aside"
            if regime in {Regime.TREND, Regime.VOLATILE}:
                return "gold_atr_trend", "NY continuation — ATR trend"
            return "gold_confluence", "NY session — confluence"

        return "gold_confluence", "Default gold confluence"

    def schedule_table(self) -> list[dict]:
        """Human-readable weekly plan for the dashboard."""
        return [
            {
                "days": "Mon–Fri",
                "utc": "07:00–13:00",
                "slot": "London",
                "strategies": "gold_atr_trend (trend) · gold_confluence (pullback) · flat if chop",
            },
            {
                "days": "Mon–Fri",
                "utc": "13:00–16:00",
                "slot": "London/NY overlap (PRIME)",
                "strategies": "gold_atr_trend (strong trend) · gold_confluence (pullback)",
            },
            {
                "days": "Mon–Thu",
                "utc": "16:00–20:00",
                "slot": "New York",
                "strategies": "gold_atr_trend / gold_confluence · flat if chop after 18:00",
            },
            {
                "days": "Fri",
                "utc": "18:00+",
                "slot": "Friday late",
                "strategies": "NO new trades",
            },
            {
                "days": "Sat–Sun / Asia",
                "utc": "outside sessions",
                "slot": "Avoid",
                "strategies": "NO new trades",
            },
            {
                "days": "Any",
                "utc": "NFP/CPI/FOMC window",
                "slot": "News blackout",
                "strategies": "NO new trades",
            },
        ]
