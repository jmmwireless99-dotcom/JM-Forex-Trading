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


def _bar_time(candles: list[dict[str, Any]]) -> int:
    return int(candles[-1]["time"])


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

    bar_time = _bar_time(candles)
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


def evaluate_breakout(
    candles: list[dict[str, Any]],
    *,
    symbol: str,
    lookback: int = 24,
    min_bars: int = 30,
) -> tuple[LabSignal | None, str | None]:
    if len(candles) < min_bars:
        return None, f"Need {min_bars}+ M5 bars (have {len(candles)})"

    window = candles[-(lookback + 1) : -1]
    if len(window) < lookback:
        return None, f"Need {lookback}-bar range"

    current = candles[-1]
    close = float(current["close"])
    hi = max(float(c["high"]) for c in window)
    lo = min(float(c["low"]) for c in window)
    bar_time = _bar_time(candles)

    if close > hi:
        return (
            LabSignal(
                side="BUY",
                symbol=symbol,
                reason=f"Breakout above {lookback}-bar high ({hi:.5f})",
                bar_time=bar_time,
            ),
            None,
        )
    if close < lo:
        return (
            LabSignal(
                side="SELL",
                symbol=symbol,
                reason=f"Breakdown below {lookback}-bar low ({lo:.5f})",
                bar_time=bar_time,
            ),
            None,
        )
    return None, f"Inside {lookback}-bar range {lo:.5f} – {hi:.5f}"


def evaluate_mean_revert(
    candles: list[dict[str, Any]],
    *,
    symbol: str,
    lookback: int = 48,
    edge_pct: float = 0.25,
    min_bars: int = 52,
) -> tuple[LabSignal | None, str | None]:
    if len(candles) < min_bars:
        return None, f"Need {min_bars}+ M5 bars (have {len(candles)})"

    window = candles[-lookback:]
    hi = max(float(c["high"]) for c in window)
    lo = min(float(c["low"]) for c in window)
    span = hi - lo
    if span <= 0:
        return None, "Flat range — no edge"

    close = float(candles[-1]["close"])
    pos = (close - lo) / span
    bar_time = _bar_time(candles)
    pct = round(pos * 100, 1)

    if pos <= edge_pct:
        return (
            LabSignal(
                side="BUY",
                symbol=symbol,
                reason=f"Range bottom {pct}% — mean revert BUY",
                bar_time=bar_time,
            ),
            None,
        )
    if pos >= 1.0 - edge_pct:
        return (
            LabSignal(
                side="SELL",
                symbol=symbol,
                reason=f"Range top {pct}% — mean revert SELL",
                bar_time=bar_time,
            ),
            None,
        )
    return None, f"Mid-range {pct}% — wait for top/bottom {int(edge_pct*100)}% zone"


def evaluate_strategy(
    strategy_id: str,
    candles: list[dict[str, Any]],
    *,
    symbol: str,
) -> tuple[LabSignal | None, str | None]:
    sid = (strategy_id or "EMA_RSI_SCALP").upper()

    if sid == "EMA_RSI_SCALP":
        return evaluate_ema_rsi(
            candles,
            symbol=symbol,
            rsi_buy=(40.0, 54.0),
            rsi_sell=(46.0, 60.0),
        )
    if sid == "EMA_RSI_TREND":
        return evaluate_ema_rsi(
            candles,
            symbol=symbol,
            rsi_buy=(36.0, 55.0),
            rsi_sell=(45.0, 64.0),
        )
    if sid == "BREAKOUT":
        return evaluate_breakout(candles, symbol=symbol)
    if sid == "MEAN_REVERT":
        lb = 36 if symbol == "EURCHF" else 48
        edge = 0.22 if symbol == "EURCHF" else 0.25
        return evaluate_mean_revert(candles, symbol=symbol, lookback=lb, edge_pct=edge)
    if sid == "EMA_RSI":
        return evaluate_ema_rsi(candles, symbol=symbol)

    return evaluate_ema_rsi(candles, symbol=symbol)
