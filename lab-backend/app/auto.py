from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from app.pair_strategies import preset_for
from app.strategy import evaluate_strategy

if TYPE_CHECKING:
    from app.accounts import LabAccount


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pip(symbol: str) -> float:
    return 0.01 if symbol == "XAUUSD" else 0.0001


def _levels_from_entry(
    side: str,
    entry: float,
    symbol: str,
    sl_pips: float,
    tp_pips: float,
) -> tuple[float, float]:
    """SL/TP anchored to actual fill price (not mid) — avoids spread skew."""
    pip = _pip(symbol)
    sl = sl_pips * pip
    tp = tp_pips * pip
    if side == "BUY":
        return entry - sl, entry + tp
    return entry + sl, entry - tp


def _bar_seconds(candles: list[dict[str, Any]]) -> int:
    if len(candles) >= 2:
        dt = int(candles[-1]["time"]) - int(candles[-2]["time"])
        if 60 <= dt <= 3600:
            return dt
    return 300


def try_auto_fill(
    acc: LabAccount,
    candles: list[dict[str, Any]],
    mid: float,
) -> dict[str, Any] | None:
    """Evaluate strategy and open a market order if flat."""
    auto = acc.auto
    if not auto.enabled:
        return None
    sym = auto.symbol.upper()
    if acc.broker.open_positions():
        auto.last_block_reason = "Open position — waiting for close"
        return None

    closed = candles[:-1] if len(candles) > 1 else candles
    if not closed:
        auto.last_block_reason = "No candle history"
        return None

    bar_time = int(closed[-1]["time"])
    if bar_time <= auto.last_bar_time:
        return None

    preset = preset_for(sym)
    bar_sec = _bar_seconds(closed)
    min_bars = int(preset.get("min_bars_between", 2))
    loss_cooldown = int(preset.get("cooldown_bars_after_loss", 3))

    if auto.last_loss_bar_time and bar_time - auto.last_loss_bar_time < loss_cooldown * bar_sec:
        bars_left = loss_cooldown - (bar_time - auto.last_loss_bar_time) // bar_sec
        auto.last_block_reason = f"Cooldown after loss ({max(1, bars_left)} M5 bars left)"
        return None

    if auto.signals:
        last_bt = int(auto.signals[0].get("bar_time") or 0)
        if last_bt and bar_time - last_bt < min_bars * bar_sec:
            auto.last_block_reason = f"Spacing entries ({min_bars} M5 bars between signals)"
            return None

    auto.last_bar_time = bar_time

    signal, block = evaluate_strategy(auto.strategy, closed, symbol=sym)
    if signal is None:
        auto.last_block_reason = block
        return None

    side = signal.side
    entry = acc.broker.entry_price(sym, side, mid)
    sl, tp = _levels_from_entry(side, entry, sym, auto.sl_pips, auto.tp_pips)
    auto.last_block_reason = None

    try:
        pos = acc.broker.open_market(
            symbol=sym,
            side=side,
            lots=auto.lots,
            stop_loss=sl,
            take_profit=tp,
        )
    except ValueError as e:
        auto.last_block_reason = str(e)
        return None

    entry_row = {
        "at": _now(),
        "side": side,
        "symbol": sym,
        "lots": auto.lots,
        "reason": signal.reason,
        "position_id": pos.id,
        "bar_time": bar_time,
    }
    auto.signals.appendleft(entry_row)
    auto.last_signal_at = entry_row["at"]
    return {"signal": signal.to_dict(), "position": pos.to_dict(), "fill": entry_row}
