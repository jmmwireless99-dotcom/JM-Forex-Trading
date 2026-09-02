from datetime import datetime, timedelta, timezone

from app.models.domain import Candle, Side
from app.strategies.asia_stops import (
    apply_sl_tp_scale,
    compute_asia_levels,
    refresh_asia_position_stops,
)
from app.strategies.entry_setup import adaptive_vol_stop_scale, true_atr


def _bars(n: int = 80, start: float = 2300.0, *, vol: float = 0.4) -> list[Candle]:
    now = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    price = start
    for i in range(n):
        o = price
        c = price + (0.15 if i % 5 else -0.05)
        h = max(o, c) + vol
        l = min(o, c) - vol
        t = now - timedelta(minutes=5 * (n - i))
        out.append(
            Candle(
                symbol="XAUUSD",
                open=o,
                high=h,
                low=l,
                close=c,
                volume=10,
                period_seconds=300,
                open_time=t,
                timestamp=t + timedelta(minutes=4, seconds=59),
                is_closed=True,
            )
        )
        price = c
    return out


def test_adaptive_vol_stop_scale_tighter_on_calm_tape():
    # Long volatile history, then very calm recent bars → ratio < 1 → mult < 1
    volatile = _bars(80, vol=1.2)
    calm = list(volatile)
    for i in range(-12, 0):
        c = calm[i]
        calm[i] = c.model_copy(
            update={
                "high": c.close + 0.08,
                "low": c.close - 0.08,
                "open": c.close - 0.02,
            }
        )
    fast = list(calm)
    for i in (-3, -2, -1):
        c = fast[i]
        fast[i] = c.model_copy(
            update={"high": c.high + 6.0, "low": c.low - 6.0, "close": c.close + 3.0}
        )
    atr = true_atr(calm, 14)
    assert atr is not None
    _, calm_mult = adaptive_vol_stop_scale(calm, atr, mult_calm=0.72, mult_fast=1.75)
    _, fast_mult = adaptive_vol_stop_scale(fast, atr, mult_calm=0.72, mult_fast=1.75)
    assert calm_mult <= 1.0
    assert fast_mult > calm_mult


def test_compute_asia_levels_calm_vs_fast():
    calm = _bars(vol=0.25)
    fast = _bars(vol=0.25)
    for i in (-3, -2, -1):
        c = fast[i]
        fast[i] = c.model_copy(
            update={"high": c.high + 5.0, "low": c.low - 5.0, "close": c.close + 2.5}
        )
    atr = true_atr(calm, 14)
    assert atr is not None
    entry = calm[-1].close
    calm_lv = compute_asia_levels(Side.BUY, entry=entry, candles=calm, atr=atr)
    fast_lv = compute_asia_levels(Side.BUY, entry=entry, candles=fast, atr=atr)
    assert abs(entry - fast_lv.stop_loss) > abs(entry - calm_lv.stop_loss)
    assert abs(fast_lv.take_profit - entry) > abs(calm_lv.take_profit - entry)


def test_apply_sl_tp_scale_widen_and_tighten():
    sl, tp = apply_sl_tp_scale(
        Side.BUY,
        entry=2400.0,
        stop_loss=2390.0,
        take_profit=2420.0,
        scale=1.2,
    )
    assert sl < 2390.0
    assert tp > 2420.0
    sl2, tp2 = apply_sl_tp_scale(
        Side.BUY,
        entry=2400.0,
        stop_loss=sl,
        take_profit=tp,
        scale=0.9,
    )
    assert sl2 > sl
    assert tp2 < tp


def test_refresh_asia_position_stops_respects_manual_scale():
    bars = _bars()
    atr = true_atr(bars, 14)
    assert atr is not None
    entry = bars[-1].close
    base = refresh_asia_position_stops(
        Side.BUY, entry=entry, candles=bars, atr=atr, sl_tp_scale=1.0
    )
    wide = refresh_asia_position_stops(
        Side.BUY, entry=entry, candles=bars, atr=atr, sl_tp_scale=1.2
    )
    assert base is not None and wide is not None
    assert abs(entry - wide.stop_loss) > abs(entry - base.stop_loss)
