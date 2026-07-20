from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from app.models.domain import Tick, utcnow


@dataclass
class SymbolState:
    symbol: str
    mid: float
    spread: float
    volatility: float
    phase: float = field(default_factory=lambda: random.random() * math.pi * 2)


class MarketDataSimulator:
    """Generates realistic-enough FX ticks for paper trading & strategy testing."""

    DEFAULTS = {
        "EURUSD": (1.0850, 0.00012, 0.00008),
        "GBPUSD": (1.2650, 0.00016, 0.00010),
        "USDJPY": (156.20, 0.012, 0.015),
        # Gold paper tape: moderate vol so ATR stops are not noise-stopped every few seconds
        "XAUUSD": (2350.0, 0.30, 0.45),
    }

    def __init__(self, symbols: list[str]) -> None:
        self._states: dict[str, SymbolState] = {}
        for symbol in symbols:
            mid, spread, vol = self.DEFAULTS.get(symbol, (1.0, 0.0002, 0.0001))
            self._states[symbol] = SymbolState(symbol, mid, spread, vol)
        self._step = 0

    def next_ticks(self) -> list[Tick]:
        self._step += 1
        ticks: list[Tick] = []
        now = utcnow()
        for state in self._states.values():
            # mild drift + mean-reverting noise
            state.phase += 0.05
            drift = math.sin(state.phase) * state.volatility * 0.35
            noise = random.gauss(0, state.volatility)
            state.mid = max(state.mid * 0.0001, state.mid + drift + noise)
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

    def last_mids(self) -> dict[str, float]:
        return {s.symbol: round(s.mid, 5) for s in self._states.values()}