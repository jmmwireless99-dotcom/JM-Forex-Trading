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
    ema_trend: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "symbol": self.symbol,
            "reason": self.reason,
            "bar_time": self.bar_time,
            "rsi": self.rsi,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "ema_trend": self.ema_trend,
        }


def _bar_time(candles: list[dict[str, Any]]) -> int:
    return int(candles[-1]["time"])


def _pip(symbol: str) -> float:
    return 0.01 if symbol == "XAUUSD" else 0.0001


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
    cur = candles[-1]
    bull_bar = float(cur["close"]) > float(cur["open"])
    bear_bar = float(cur["close"]) < float(cur["open"])

    if bullish and rsi_buy[0] <= rv <= rsi_buy[1]:
        if not bull_bar:
            return None, f"BUY setup but bearish M5 bar (RSI {rv:.1f})"
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
        if not bear_bar:
            return None, f"SELL setup but bullish M5 bar (RSI {rv:.1f})"
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


def evaluate_gold_ema_rsi(
    candles: list[dict[str, Any]],
    *,
    symbol: str,
    ema_fast: int = 20,
    ema_medium: int = 50,
    ema_slow: int = 200,
    rsi_period: int = 8,
    rsi_oversold: float = 40.0,
    rsi_overbought: float = 60.0,
    breakout_min_pips: float = 15.0,
    min_bars: int = 210,
) -> tuple[LabSignal | None, str | None]:
    """Gold M5 stack from review: EMA 20/50/200 + RSI(8) + min breakout candle."""
    if len(candles) < min_bars:
        return None, f"Need {min_bars}+ M5 bars for EMA{ema_slow} (have {len(candles)})"

    closes = [float(c["close"]) for c in candles]
    e_fast = ema(closes, ema_fast)
    e_med = ema(closes, ema_medium)
    e_slow = ema(closes, ema_slow)
    rs = rsi(closes, rsi_period)

    i = len(closes) - 1
    ef, em, es, rv = e_fast[i], e_med[i], e_slow[i], rs[i]
    if ef is None or em is None or es is None or rv is None:
        return None, "Indicators warming up (EMA20/50/200 + RSI8)"

    cur = candles[-1]
    close = float(cur["close"])
    open_ = float(cur["open"])
    pip = _pip(symbol)
    body_pips = abs(close - open_) / pip
    range_pips = (float(cur["high"]) - float(cur["low"])) / pip
    candle_pips = max(body_pips, range_pips)
    bar_time = _bar_time(candles)

    if candle_pips < breakout_min_pips:
        return (
            None,
            f"Signal candle too small ({candle_pips:.1f}p, need {breakout_min_pips:.0f}p min)",
        )

    bull_bar = close > open_
    bear_bar = close < open_
    uptrend = ef > em and close > es
    downtrend = ef < em and close < es

    # Oversold bounce: RSI 40–55 in uptrend · Overbought fade: RSI 45–60 in downtrend
    if uptrend and bull_bar and rsi_oversold <= rv <= 55.0:
        return (
            LabSignal(
                side="BUY",
                symbol=symbol,
                reason=(
                    f"Gold BUY · EMA{ema_fast}>{ema_medium} · above EMA{ema_slow} · "
                    f"RSI{rsi_period} {rv:.1f} bounce · candle {candle_pips:.0f}p"
                ),
                bar_time=bar_time,
                rsi=round(rv, 2),
                ema_fast=round(ef, 2),
                ema_slow=round(em, 2),
                ema_trend=round(es, 2),
            ),
            None,
        )
    if downtrend and bear_bar and 45.0 <= rv <= rsi_overbought:
        return (
            LabSignal(
                side="SELL",
                symbol=symbol,
                reason=(
                    f"Gold SELL · EMA{ema_fast}<{ema_medium} · below EMA{ema_slow} · "
                    f"RSI{rsi_period} {rv:.1f} exhaustion · candle {candle_pips:.0f}p"
                ),
                bar_time=bar_time,
                rsi=round(rv, 2),
                ema_fast=round(ef, 2),
                ema_slow=round(em, 2),
                ema_trend=round(es, 2),
            ),
            None,
        )

    if uptrend and not bull_bar:
        return None, f"Uptrend but bearish M5 bar (RSI {rv:.1f})"
    if downtrend and not bear_bar:
        return None, f"Downtrend but bullish M5 bar (RSI {rv:.1f})"
    if uptrend:
        return None, f"Uptrend but RSI {rv:.1f} outside bounce {rsi_oversold}–55"
    if downtrend:
        return None, f"Downtrend but RSI {rv:.1f} outside fade 45–{rsi_overbought:.0f}"
    return None, f"No gold trend · RSI {rv:.1f} · wait for EMA20/50/200 alignment"


def evaluate_breakout(
    candles: list[dict[str, Any]],
    *,
    symbol: str,
    lookback: int = 24,
    min_bars: int = 30,
    buffer_pct: float = 0.02,
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
    span = hi - lo
    if span <= 0:
        return None, "Flat range — no breakout levels"
    buffer = span * buffer_pct
    bar_time = _bar_time(candles)

    if close > hi + buffer:
        return (
            LabSignal(
                side="BUY",
                symbol=symbol,
                reason=f"Breakout above {lookback}-bar high ({hi:.5f}) + buffer",
                bar_time=bar_time,
            ),
            None,
        )
    if close < lo - buffer:
        return (
            LabSignal(
                side="SELL",
                symbol=symbol,
                reason=f"Breakdown below {lookback}-bar low ({lo:.5f}) + buffer",
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
    min_range_pips: float = 12.0,
) -> tuple[LabSignal | None, str | None]:
    if len(candles) < min_bars:
        return None, f"Need {min_bars}+ M5 bars (have {len(candles)})"

    window = candles[-lookback:]
    hi = max(float(c["high"]) for c in window)
    lo = min(float(c["low"]) for c in window)
    span = hi - lo
    pip = _pip(symbol)
    span_pips = span / pip if pip else 0
    if span <= 0:
        return None, "Flat range — no edge"
    if span_pips < min_range_pips:
        return None, f"Range too tight ({span_pips:.1f} pips, need {min_range_pips:.0f}+)"

    closes = [float(c["close"]) for c in candles]
    e_fast = ema(closes, 20)
    e_slow = ema(closes, 50)
    i = len(closes) - 1
    ef, es = e_fast[i], e_slow[i]

    close = float(candles[-1]["close"])
    cur = candles[-1]
    bull_bar = close > float(cur["open"])
    bear_bar = close < float(cur["open"])
    pos = (close - lo) / span
    bar_time = _bar_time(candles)
    pct = round(pos * 100, 1)

    if pos <= edge_pct:
        if ef is not None and es is not None and ef < es and close < ef:
            return None, f"Range bottom but downtrend — skip BUY ({pct}%)"
        if not bull_bar:
            return None, f"Range bottom {pct}% but bearish bar — skip fade"
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
        if ef is not None and es is not None and ef > es and close > ef:
            return None, f"Range top but uptrend — skip SELL ({pct}%)"
        if not bear_bar:
            return None, f"Range top {pct}% but bullish bar — skip fade"
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
        from app.pair_strategies import preset_for

        p = preset_for(symbol)
        return evaluate_gold_ema_rsi(
            candles,
            symbol=symbol,
            ema_fast=int(p.get("ema_fast", 20)),
            ema_medium=int(p.get("ema_medium", 50)),
            ema_slow=int(p.get("ema_slow", 200)),
            rsi_period=int(p.get("rsi_period", 8)),
            rsi_oversold=float(p.get("rsi_oversold", 40)),
            rsi_overbought=float(p.get("rsi_overbought", 60)),
            breakout_min_pips=float(p.get("breakout_min_pips", 15)),
        )
    if sid == "GOLD_EMA_RSI":
        from app.pair_strategies import preset_for

        p = preset_for(symbol)
        return evaluate_gold_ema_rsi(
            candles,
            symbol=symbol,
            ema_fast=int(p.get("ema_fast", 20)),
            ema_medium=int(p.get("ema_medium", 50)),
            ema_slow=int(p.get("ema_slow", 200)),
            rsi_period=int(p.get("rsi_period", 8)),
            rsi_oversold=float(p.get("rsi_oversold", 40)),
            rsi_overbought=float(p.get("rsi_overbought", 60)),
            breakout_min_pips=float(p.get("breakout_min_pips", 15)),
        )
    if sid == "BREAKOUT":
        return evaluate_breakout(candles, symbol=symbol, buffer_pct=0.015)
    if sid == "MEAN_REVERT":
        if symbol == "EURCHF":
            return evaluate_mean_revert(
                candles,
                symbol=symbol,
                lookback=36,
                edge_pct=0.15,
                min_range_pips=18.0,
            )
        return evaluate_mean_revert(
            candles,
            symbol=symbol,
            lookback=48,
            edge_pct=0.18,
            min_range_pips=15.0,
        )
    if sid == "EMA_RSI":
        return evaluate_ema_rsi(candles, symbol=symbol)

    return evaluate_ema_rsi(candles, symbol=symbol)
