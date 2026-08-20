from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.indicators import ema, rsi

Side = Literal["BUY", "SELL"]


@dataclass
class LabSignal:
    side: Side
    symbol: str
    reason: str
    bar_time: int
    rsi: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "symbol": self.symbol,
            "reason": self.reason,
            "bar_time": self.bar_time,
            "rsi": self.rsi,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
        }


def evaluate_ema_rsi(
    candles: list[dict[str, Any]],
    *,
    symbol: str,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_period: int = 14,
    rsi_buy: tuple[float, float] = (38.0, 52.0),
    rsi_sell: tuple[float, float] = (48.0, 62.0),
    min_bars: int = 55,
) -> tuple[LabSignal | None, str | None]:
    """Simplified JM FX EMA+RSI scalp on closed M5 bars."""
    if len(candles) < min_bars:
        return None, f"Need {min_bars}+ M5 bars (have {len(candles)})"

    closes = [float(c["close"]) for c in candles]
    e_fast = ema(closes, ema_fast)
    e_slow = ema(closes, ema_slow)
    rs = rsi(closes, rsi_period)

    i = len(closes) - 1
    ef, es, rv = e_fast[i], e_slow[i], rs[i]
    if ef is None or es is None or rv is None:
        return None, "Indicators warming up"

    bar_time = int(candles[i]["time"])
    bullish = ef > es
    bearish = ef < es

    if bullish and rsi_buy[0] <= rv <= rsi_buy[1]:
        return (
            LabSignal(
                side="BUY",
                symbol=symbol,
                reason=f"EMA{ema_fast}>{ema_slow} · RSI {rv:.1f} in buy zone",
                bar_time=bar_time,
                rsi=round(rv, 2),
                ema_fast=round(ef, 5),
                ema_slow=round(es, 5),
            ),
            None,
        )
    if bearish and rsi_sell[0] <= rv <= rsi_sell[1]:
        return (
            LabSignal(
                side="SELL",
                symbol=symbol,
                reason=f"EMA{ema_fast}<{ema_slow} · RSI {rv:.1f} in sell zone",
                bar_time=bar_time,
                rsi=round(rv, 2),
                ema_fast=round(ef, 5),
                ema_slow=round(es, 5),
            ),
            None,
        )

    if bullish:
        return None, f"BUY trend but RSI {rv:.1f} outside {rsi_buy[0]}-{rsi_buy[1]}"
    if bearish:
        return None, f"SELL trend but RSI {rv:.1f} outside {rsi_sell[0]}-{rsi_sell[1]}"
    return None, "EMA flat — no trend"
