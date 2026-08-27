"""AI_ML — first-class FX strategy: session child setup + Machine Learning filter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.models.domain import Candle, Signal, Tick
from app.strategies.auto_router import AutoStrategyRouter
from app.strategies.base import Strategy
from app.strategies.ema_rsi_scalp import EmaRsiScalpStrategy
from app.strategies.ema_vwap_scalp import EmaVwapScalpStrategy
from app.strategies.liquidity_sweep_smc import LiquiditySweepSmcStrategy

if TYPE_CHECKING:
    from app.ai.advisor import TradeAdvisor


class AIMLStrategy(Strategy):
    """Session-routed scalp stack with AI & Machine Learning entry filter.

    Flow:
    1. Pick child strategy from session map (EMA_RSI / SMC / VWAP)
    2. Generate child signal on M5 close
    3. Score with ML — emit only TAKE / CAUTION (SKIP is blocked here)
    """

    name = "AI_ML"
    candle_driven = True

    _CHILD_MAP = {
        "asia": EmaRsiScalpStrategy.name,
        "london": EmaRsiScalpStrategy.name,
        "london_wind_down": EmaRsiScalpStrategy.name,
        "london_close": EmaRsiScalpStrategy.name,
        "london_ny_overlap": LiquiditySweepSmcStrategy.name,
        "new_york": EmaVwapScalpStrategy.name,
        "off_hours": EmaRsiScalpStrategy.name,
    }

    def __init__(self, lookback: int = 260) -> None:
        super().__init__(lookback=lookback)
        self.router = AutoStrategyRouter()
        self._children: dict[str, Strategy] = {
            EmaRsiScalpStrategy.name: EmaRsiScalpStrategy(lookback=lookback),
            LiquiditySweepSmcStrategy.name: LiquiditySweepSmcStrategy(lookback=lookback),
            EmaVwapScalpStrategy.name: EmaVwapScalpStrategy(lookback=lookback),
        }
        self.advisor: TradeAdvisor | None = None
        self.active_child_name: str | None = None
        self.last_advice: dict[str, Any] | None = None
        self.last_block_reason: str | None = None
        self.last_checklist: list[str] = []
        self._structure_bars: list[Candle] = []
        self.allow_caution = True

    def set_advisor(self, advisor: TradeAdvisor | None) -> None:
        self.advisor = advisor

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)
        for child in self._children.values():
            if hasattr(child, "set_structure_bars"):
                child.set_structure_bars(candles)

    def feed(self, tick: Tick) -> None:
        super().feed(tick)
        for child in self._children.values():
            child.feed(tick)

    def feed_bar(self, candle: Candle) -> None:
        super().feed_bar(candle)
        for child in self._children.values():
            child.feed_bar(candle)

    def _child_for(self, tick: Tick) -> tuple[Strategy | None, str | None]:
        decision = self.router.decide(tick.timestamp, self.prices(tick.symbol))
        if not decision.allow_trading:
            self.last_block_reason = decision.reason or "AI_ML stand aside"
            return None, None
        name = self._CHILD_MAP.get(decision.slot)
        if not name or name not in self._children:
            self.last_block_reason = (
                f"AI_ML: no child for session {decision.slot}"
            )
            return None, None
        return self._children[name], name

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        self.last_block_reason = None
        self.last_advice = None
        child, child_name = self._child_for(tick)
        self.active_child_name = child_name
        if child is None or child_name is None:
            self.last_checklist = ["AI_ML: no session child"]
            return None

        if hasattr(child, "set_structure_bars"):
            child.set_structure_bars(self._structure_bars or candles)

        if getattr(child, "candle_driven", False):
            signal = child.on_bar(candles, tick)
        else:
            signal = child.evaluate(tick)

        self.last_checklist = list(getattr(child, "last_checklist", []) or [])
        self.last_checklist.insert(0, f"AI_ML child={child_name}")

        if signal is None:
            self.last_block_reason = getattr(child, "last_block_reason", None) or (
                f"AI_ML/{child_name}: no setup"
            )
            return None

        smc_child = (
            child
            if child_name == LiquiditySweepSmcStrategy.name
            else None
        )

        if self.advisor is None or not self.advisor.enabled:
            if smc_child is not None:
                smc_child.commit_pending_signal()
            signal.strategy = f"AI_ML/{child_name}"
            signal.reason = f"AI_ML · {signal.reason}"
            return signal

        entry = tick.ask if signal.side.value == "BUY" else tick.bid
        if signal.limit_price is not None:
            entry = signal.limit_price
        advice = self.advisor.advise_signal(signal, entry=entry)
        self.last_advice = advice.as_dict()

        if advice.action == "SKIP" or (
            advice.action == "CAUTION" and not self.allow_caution
        ):
            if smc_child is not None:
                smc_child.rollback_pending_signal()
            self.last_block_reason = (
                f"AI_ML {advice.action} p={advice.win_probability:.0%} · "
                + (advice.reasons[0] if advice.reasons else "ML filter")
            )
            self.last_checklist.append(self.last_block_reason)
            return None

        if smc_child is not None:
            smc_child.commit_pending_signal()

        signal.strategy = f"AI_ML/{child_name}"
        signal.reason = (
            f"AI_ML {advice.action} p={advice.win_probability:.0%} · {signal.reason}"
        )
        signal.strength = max(float(signal.strength or 0.5), float(advice.win_probability))
        self.last_checklist.append(
            f"AI_ML {advice.action} p={advice.win_probability:.0%} conf={advice.confidence:.0%}"
        )
        return signal
