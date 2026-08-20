from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from app.strategy import LabSignal, evaluate_ema_rsi

if TYPE_CHECKING:
    from app.accounts import LabAccount


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pip(symbol: str) -> float:
    return 0.01 if symbol == "XAUUSD" else 0.0001


def _levels(side: str, mid: float, symbol: str, sl_pips: float, tp_pips: float) -> tuple[float | None, float | None]:
    pip = _pip(symbol)
    sl = sl_pips * pip
    tp = tp_pips * pip
    if side == "BUY":
        return mid - sl, mid + tp
    return mid + sl, mid - tp


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
    auto.last_bar_time = bar_time

    signal, block = evaluate_ema_rsi(closed, symbol=sym)
    if signal is None:
        auto.last_block_reason = block
        return None

    auto.last_block_reason = None
    side = signal.side
    sl, tp = _levels(side, mid, sym, auto.sl_pips, auto.tp_pips)
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

    entry = {
        "at": _now(),
        "side": side,
        "symbol": sym,
        "lots": auto.lots,
        "reason": signal.reason,
        "position_id": pos.id,
        "bar_time": bar_time,
    }
    auto.signals.appendleft(entry)
    auto.last_signal_at = entry["at"]
    return {"signal": signal.to_dict(), "position": pos.to_dict(), "fill": entry}
