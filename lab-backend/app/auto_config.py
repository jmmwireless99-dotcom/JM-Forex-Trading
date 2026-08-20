from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AutoConfig:
    enabled: bool = False
    symbol: str = "EURUSD"
    lots: float = 0.01
    sl_pips: float = 15.0
    tp_pips: float = 30.0
    strategy: str = "EMA_RSI"
    last_bar_time: int = 0
    last_signal_at: str | None = None
    last_block_reason: str | None = None
    signals: deque = field(default_factory=lambda: deque(maxlen=30))

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "symbol": self.symbol,
            "lots": self.lots,
            "sl_pips": self.sl_pips,
            "tp_pips": self.tp_pips,
            "strategy": self.strategy,
            "last_bar_time": self.last_bar_time,
            "last_signal_at": self.last_signal_at,
            "last_block_reason": self.last_block_reason,
            "recent_signals": list(self.signals),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AutoConfig:
        if not data:
            return cls()
        sigs = deque((data.get("recent_signals") or [])[-30:], maxlen=30)
        return cls(
            enabled=bool(data.get("enabled")),
            symbol=str(data.get("symbol") or "EURUSD").upper(),
            lots=float(data.get("lots") or 0.01),
            sl_pips=float(data.get("sl_pips") or 15),
            tp_pips=float(data.get("tp_pips") or 30),
            strategy=str(data.get("strategy") or "EMA_RSI"),
            last_bar_time=int(data.get("last_bar_time") or 0),
            last_signal_at=data.get("last_signal_at"),
            last_block_reason=data.get("last_block_reason"),
            signals=sigs,
        )
