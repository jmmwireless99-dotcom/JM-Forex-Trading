from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timezone

from app.models.domain import Tick, utcnow


LiveMidProvider = Callable[[str], float | None]


@dataclass
class SymbolState:
    symbol: str
    mid: float
    spread: float
    volatility: float
    phase: float = field(default_factory=lambda: random.random() * math.pi * 2)
    # Session scenario state (paper Judas / SMC validation)
    scenario: str | None = None
    scenario_step: int = 0
    asia_high: float | None = None
    asia_low: float | None = None
    session_anchor: float | None = None


class MarketDataSimulator:
    """Generates FX ticks for paper trading & strategy testing.

    Includes light session scenarios so London Judas / SMC can fire on paper
    (plain random walk almost never forms sweep + ChoCH + FVG confluence).

    When a live_mid_provider is set (paper sync to gold), XAUUSD mid tracks
    the real market with small noise — desk prices match TradingView.
    """

    DEFAULTS = {
        "EURUSD": (1.0850, 0.00012, 0.00008),
        "GBPUSD": (1.2650, 0.00016, 0.00010),
        "USDJPY": (156.20, 0.012, 0.015),
        # Fallback only — normally overwritten by live gold sync (~4100+)
        "XAUUSD": (2350.0, 0.30, 0.45),
    }

    def __init__(
        self,
        symbols: list[str],
        *,
        live_mid_provider: LiveMidProvider | None = None,
        live_noise: float = 0.08,
    ) -> None:
        self._states: dict[str, SymbolState] = {}
        self._live_mid_provider = live_mid_provider
        self._live_noise = max(0.0, float(live_noise))
        for symbol in symbols:
            mid, spread, vol = self.DEFAULTS.get(symbol, (1.0, 0.0002, 0.0001))
            self._states[symbol] = SymbolState(symbol, mid, spread, vol)
        self._step = 0
        # Best-effort pin on construct so first ticks are already near live.
        self.pull_live_mids(force=True)

    def set_live_mid_provider(self, provider: LiveMidProvider | None) -> None:
        self._live_mid_provider = provider
        self.pull_live_mids(force=True)

    def pull_live_mids(self, *, force: bool = False) -> dict[str, float]:
        """Sync symbol mids from live provider. Returns updated symbol→mid."""
        updated: dict[str, float] = {}
        if self._live_mid_provider is None:
            return updated
        for symbol, state in self._states.items():
            if symbol != "XAUUSD" and not force:
                continue
            try:
                live = self._live_mid_provider(symbol)
            except Exception:
                live = None
            if live is None or not (1000 < float(live) < 20000):
                continue
            self.sync_mid(symbol, float(live))
            updated[symbol] = float(live)
        return updated

    def next_ticks(self) -> list[Tick]:
        self._step += 1
        # Refresh live gold anchor periodically (provider is cached ~20s).
        if self._live_mid_provider and self._step % 15 == 1:
            self.pull_live_mids(force=True)

        ticks: list[Tick] = []
        now = utcnow()
        for state in self._states.values():
            live_tracked = False
            if self._live_mid_provider and state.symbol == "XAUUSD":
                # Still run paper scenarios (Judas/SMC) on top of live gold.
                self._maybe_start_scenario(state, now)
                if state.scenario is not None:
                    delta = self._scenario_delta(state, now)
                    if delta is None:
                        delta = 0.0
                    state.mid = max(state.mid * 0.0001, state.mid + delta)
                    live_tracked = True
                elif state.session_anchor and state.session_anchor > 1000:
                    noise = random.gauss(0, self._live_noise) if self._live_noise else 0.0
                    state.mid = float(state.session_anchor) + noise
                    live_tracked = True

            if not live_tracked:
                if state.symbol == "XAUUSD":
                    self._maybe_start_scenario(state, now)
                    delta = self._scenario_delta(state, now)
                else:
                    delta = None

                if delta is None:
                    state.phase += 0.05
                    drift = math.sin(state.phase) * state.volatility * 0.35
                    noise = random.gauss(0, state.volatility)
                    if state.session_anchor is None:
                        state.session_anchor = state.mid
                    pull = (state.session_anchor - state.mid) * 0.08
                    delta = drift + noise + pull

                state.mid = max(state.mid * 0.0001, state.mid + delta)

            half = state.spread / 2
            bid = state.mid - half
            ask = state.mid + half
            ticks.append(
                Tick(
                    symbol=state.symbol,
                    bid=round(bid, 5 if state.symbol != "XAUUSD" else 2),
                    ask=round(ask, 5 if state.symbol != "XAUUSD" else 2),
                    mid=round(state.mid, 5 if state.symbol != "XAUUSD" else 2),
                    timestamp=now,
                )
            )
        return ticks

    def _maybe_start_scenario(self, state: SymbolState, now) -> None:
        if state.scenario is not None:
            return
        utc = now.astimezone(timezone.utc)
        if utc.weekday() >= 5:
            return
        hour = utc.hour
        # Track Asia box roughly for later SMC sweeps.
        # Do not return here — Asia session also needs EMA pullback demos below.
        if 0 <= hour < 7:
            if state.session_anchor is None:
                state.session_anchor = state.mid
            state.asia_high = max(state.asia_high or state.mid, state.mid)
            state.asia_low = min(state.asia_low or state.mid, state.mid)
        # Overlap: SMC-style liquidity grab
        if 13 <= hour < 16 and self._step % 150 == 0:
            if state.asia_high is None:
                state.asia_high = state.mid + 1.5
                state.asia_low = state.mid - 1.5
            state.scenario = "smc_sweep_sell" if (self._step // 150) % 2 == 0 else "smc_sweep_buy"
            state.scenario_step = 0
        # Asia / NY: EMA pullback setups — less frequent to avoid churn losses
        elif (0 <= hour < 7 or 16 <= hour < 20) and self._step % 300 == 0:
            state.scenario = (
                "ema_pullback_buy" if (self._step // 300) % 2 == 0 else "ema_pullback_sell"
            )
            state.scenario_step = 0
            if state.session_anchor is None:
                state.session_anchor = state.mid
            state.mid = float(state.session_anchor)

    def _scenario_delta(self, state: SymbolState, now) -> float | None:
        if state.scenario is None:
            return None
        step = state.scenario_step
        state.scenario_step += 1
        vol = state.volatility

        if state.scenario == "smc_sweep_sell":
            # Grab above recent high (~$1.0), reject, then bearish follow-through
            target = (state.asia_high or state.mid) + 1.0
            if step < 8:
                return max(0.1, (target - state.mid) * 0.45) + random.gauss(0, vol * 0.15)
            if step < 20:
                return -0.14 - abs(random.gauss(0, vol * 0.2))
            if step < 35:
                return -0.05 + random.gauss(0, vol * 0.12)
            state.scenario = None
            return None

        if state.scenario == "smc_sweep_buy":
            target = (state.asia_low or state.mid) - 1.0
            if step < 8:
                return min(-0.1, (target - state.mid) * 0.45) + random.gauss(0, vol * 0.15)
            if step < 20:
                return 0.14 + abs(random.gauss(0, vol * 0.2))
            if step < 35:
                return 0.05 + random.gauss(0, vol * 0.12)
            state.scenario = None
            return None

        if state.scenario == "ema_pullback_buy":
            # Dip then reclaim — move far enough to refresh RSI into the buy band
            target = (state.session_anchor or state.mid) - 1.5
            if step < 25:
                return min(-0.08, (target - state.mid) * 0.35) + random.gauss(0, vol * 0.08)
            if step < 55:
                return 0.14 + abs(random.gauss(0, vol * 0.06))
            if step < 75:
                return 0.05 + random.gauss(0, vol * 0.06)
            state.scenario = None
            return None

        if state.scenario == "ema_pullback_sell":
            # Rally then reject — lift RSI into sell band before the drop
            target = (state.session_anchor or state.mid) + 1.5
            if step < 25:
                return max(0.08, (target - state.mid) * 0.35) + random.gauss(0, vol * 0.08)
            if step < 55:
                return -0.14 - abs(random.gauss(0, vol * 0.06))
            if step < 75:
                return -0.05 + random.gauss(0, vol * 0.06)
            state.scenario = None
            return None

        state.scenario = None
        return None

    def last_mids(self) -> dict[str, float]:
        return {s.symbol: round(s.mid, 5) for s in self._states.values()}

    def sync_mid(self, symbol: str, mid: float) -> None:
        """Align simulator mid (+ session anchor) to seeded candle close."""
        state = self._states.get(symbol.upper())
        if state is None:
            return
        state.mid = float(mid)
        state.session_anchor = float(mid)
        state.asia_high = float(mid) + 0.8
        state.asia_low = float(mid) - 0.8
