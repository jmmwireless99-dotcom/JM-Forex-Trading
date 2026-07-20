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
      Entries evaluate on closed M5 bars only (not ticks).
      Mon–Fri 00–07  Asia       → asia_range_scalp if ranging; flat if trending
      Mon–Fri 07–13  London     → ATR trend / confluence; range/pullback → gold_sr_scalp
      Mon–Fri 13–16  Overlap    → ATR trend if strong; pullback/range → gold_sr_scalp
      Mon–Fri 16–18  NY         → ATR trend / gold_sr_scalp (range/pullback)
      Mon–Fri 18–20  NY late    → confluence if trend; gold_sr_scalp if pullback; else flat
      Fri 18+ / weekend / off   → no new trades
      News blackout             → no new trades
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

        # Weekend / off-hours hard block (Asia is handled below as scalp window)
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

        # Asia ranging scalp — only when tape is quiet (not breaking out)
        if session.tier == SessionTier.ASIA:
            if regime in {Regime.RANGE, Regime.PULLBACK} and (
                adx_v is None or adx_v <= self.min_trade_adx
            ):
                decision = AutoDecision(
                    True,
                    "asia_range_scalp",
                    Regime.RANGE,
                    session.label,
                    day,
                    utc.weekday(),
                    hour,
                    session.tier.value,
                    "Asia ranging candles — Donchian/RSI fade scalp",
                    adx_v,
                    atr_v,
                )
            else:
                decision = AutoDecision(
                    False,
                    None,
                    Regime.BLOCKED,
                    session.label,
                    day,
                    utc.weekday(),
                    hour,
                    session.tier.value,
                    "Asia but not ranging — stand aside (breakout risk)",
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
        # London/NY chop → S/R supply-demand scalp (Asia has its own range path).
        if regime == Regime.RANGE:
            return (
                "gold_sr_scalp",
                f"{slot}: range/chop — S/R supply-demand scalp",
            )

        if tier == SessionTier.PRIME:
            if regime in {Regime.TREND, Regime.VOLATILE}:
                return (
                    "gold_atr_trend",
                    "Overlap + strong trend — ATR trend strategy",
                )
            # PULLBACK → S/R scalp
            return (
                "gold_sr_scalp",
                "Overlap pullback — S/R supply-demand scalp",
            )

        if slot == "london":
            if regime == Regime.TREND:
                return "gold_atr_trend", "London trend day — ATR trend"
            return "gold_sr_scalp", "London pullback — S/R supply-demand scalp"

        if slot == "new_york":
            if hour >= 18:
                if regime in {Regime.TREND, Regime.VOLATILE}:
                    return "gold_confluence", "Late NY — confluence only if trend continues"
                if regime == Regime.PULLBACK:
                    return "gold_sr_scalp", "Late NY pullback — S/R supply-demand scalp"
                return None, "Late NY without trend — stand aside"
            if regime in {Regime.TREND, Regime.VOLATILE}:
                return "gold_atr_trend", "NY continuation — ATR trend"
            return "gold_sr_scalp", "NY pullback — S/R supply-demand scalp"

        if regime == Regime.PULLBACK:
            return "gold_sr_scalp", "Default pullback — S/R supply-demand scalp"
        return "gold_confluence", "Default gold confluence"

    def session_default(self, ts: datetime) -> dict:
        """Recommended strategy from session clock alone (before regime refine)."""
        utc = ts.astimezone(timezone.utc)
        session = classify_session(utc)
        day = DAY_NAMES[utc.weekday()]
        hour = utc.hour

        if session.tier == SessionTier.AVOID or (utc.weekday() == 4 and hour >= 18):
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": None,
                "mode": "stand_aside",
                "reason": session.reason
                if session.tier == SessionTier.AVOID
                else "Friday after 18:00 UTC — no new gold trades",
            }
        if session.tier == SessionTier.ASIA:
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": "asia_range_scalp",
                "mode": "auto_transfer",
                "reason": "Asia/Tokyo ranging window — asia_range_scalp",
            }
        if session.tier == SessionTier.PRIME:
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": "gold_atr_trend",
                "mode": "auto_transfer",
                "reason": (
                    "London/NY overlap — prefer gold_atr_trend "
                    "(fallback gold_sr_scalp on range/pullback)"
                ),
            }
        if session.label == "london":
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": "gold_confluence",
                "mode": "auto_transfer",
                "reason": (
                    "London session — gold_confluence / ATR if trend "
                    "(fallback gold_sr_scalp on range/pullback)"
                ),
            }
        if session.label == "new_york":
            return {
                "session": session.label,
                "tier": session.tier.value,
                "day": day,
                "hour_utc": hour,
                "strategy": "gold_atr_trend" if hour < 18 else "gold_confluence",
                "mode": "auto_transfer",
                "reason": "New York session — ATR/confluence by regime",
            }
        return {
            "session": session.label,
            "tier": session.tier.value,
            "day": day,
            "hour_utc": hour,
            "strategy": "gold_confluence",
            "mode": "auto_transfer",
            "reason": "Default — gold_confluence",
        }

    def recommend(self, ts: datetime, prices: list[float]) -> dict:
        """Full recommendation: session default refined by live regime decision."""
        base = self.session_default(ts)
        decision = self.decide(ts, prices)
        return {
            **base,
            "regime": decision.regime.value,
            "allow_trading": decision.allow_trading,
            "strategy": decision.strategy if decision.allow_trading else base.get("strategy"),
            "active_pick": decision.strategy,
            "stand_aside": not decision.allow_trading,
            "reason": decision.reason,
            "adx": decision.adx,
            "atr": decision.atr,
            "transfer_to": (
                decision.strategy
                if decision.allow_trading and decision.strategy
                else base.get("strategy")
            ),
        }

    def schedule_table(self) -> list[dict]:
        """Human-readable weekly plan for the dashboard."""
        return [
            {
                "days": "Mon–Fri",
                "utc": "07:00–13:00",
                "slot": "London",
                "strategies": (
                    "gold_atr_trend (trend) · gold_sr_scalp (range/pullback S/R)"
                ),
            },
            {
                "days": "Mon–Fri",
                "utc": "13:00–16:00",
                "slot": "London/NY overlap (PRIME)",
                "strategies": (
                    "gold_atr_trend (strong trend) · gold_sr_scalp (range/pullback)"
                ),
            },
            {
                "days": "Mon–Thu",
                "utc": "16:00–20:00",
                "slot": "New York",
                "strategies": (
                    "gold_atr_trend / gold_sr_scalp · confluence if late trend · "
                    "flat only if dead after 18:00"
                ),
            },
            {
                "days": "Fri",
                "utc": "18:00+",
                "slot": "Friday late",
                "strategies": "NO new trades",
            },
            {
                "days": "Mon–Fri",
                "utc": "00:00–07:00",
                "slot": "Asia / Tokyo",
                "strategies": "asia_range_scalp (ranging) · FLAT if ADX/trend wakes up",
            },
            {
                "days": "Sat–Sun / 20–24 UTC",
                "utc": "weekend / off-hours",
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
