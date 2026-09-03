from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from app.accounts import LabAccountStore
from app.auto import try_auto_fill
from app.feed import SUPPORTED, fetch_candles, fetch_quote_live

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
store = LabAccountStore(DATA_DIR / "lab_accounts.json")
_ticks: dict[str, dict] = {}
_running = False
_candle_cache: dict[str, tuple[float, list]] = {}
_AUTO_CHECK_EVERY = 60.0
_TICK_EVERY = 1.0
_DEFAULT_CANDLE_LIMIT = 120


def _candle_limit(sym: str) -> int:
    return _DEFAULT_CANDLE_LIMIT


def get_ticks() -> dict[str, dict]:
    return dict(_ticks)


def is_engine_running() -> bool:
    return _running


def _active_symbols() -> set[str]:
    """Pairs with auto-trading or open positions — refresh these every tick loop."""
    out: set[str] = set()
    for acc in store.all_accounts():
        if acc.auto.enabled:
            out.add(acc.auto.symbol.upper())
        for p in acc.broker.open_positions():
            out.add(p.symbol.upper())
    return out


def _last_closed_bar_time(candles: list) -> int:
    closed = candles[:-1] if len(candles) > 1 else candles
    if not closed:
        return 0
    return int(closed[-1]["time"])


async def _refresh_symbol(sym: str) -> None:
    q = await asyncio.to_thread(fetch_quote_live, sym)
    _ticks[sym] = q

    candles: list = []
    now = time.monotonic()
    cached = _candle_cache.get(sym)
    if cached and now - cached[0] < _AUTO_CHECK_EVERY:
        candles = cached[1]
    else:
        try:
            payload = await asyncio.to_thread(
                fetch_candles, sym, interval="5", limit=_candle_limit(sym)
            )
            candles = payload.get("candles") or []
            _candle_cache[sym] = (now, candles)
        except Exception as e:
            log.warning("lab auto candles %s: %s", sym, e)

    last_bar = _last_closed_bar_time(candles)
    changed = False

    for acc in store.all_accounts():
        closed_pos = acc.broker.update_tick(sym, q["mid"])
        for pos in closed_pos:
            if (pos.realized_pnl or 0) < 0 and last_bar:
                acc.auto.last_loss_bar_time = last_bar
                changed = True

    if candles:
        for acc in store.all_accounts():
            if not acc.auto.enabled or acc.auto.symbol.upper() != sym:
                continue
            if try_auto_fill(acc, candles, q["mid"]):
                changed = True

    if changed:
        store.persist()


async def _maybe_run_auto(sym: str, mid: float) -> None:
    """Legacy hook — auto runs inside _refresh_symbol when candles are cached."""
    if not any(a.auto.enabled and a.auto.symbol.upper() == sym for a in store.all_accounts()):
        return
    now = time.monotonic()
    cached = _candle_cache.get(sym)
    if not cached or now - cached[0] >= _AUTO_CHECK_EVERY:
        return
    candles = cached[1]
    changed = False
    for acc in store.all_accounts():
        if not acc.auto.enabled or acc.auto.symbol.upper() != sym:
            continue
        if try_auto_fill(acc, candles, mid):
            changed = True
    if changed:
        store.persist()


async def tick_loop() -> None:
    global _running
    _running = True
    idle_idx = 0
    while _running:
        active = _active_symbols()
        try:
            if active:
                await asyncio.gather(*[_refresh_symbol(sym) for sym in sorted(active)])
            else:
                sym = SUPPORTED[idle_idx % len(SUPPORTED)]
                idle_idx += 1
                await _refresh_symbol(sym)
            store.persist()
        except Exception as e:
            log.warning("lab tick loop: %s", e)
        await asyncio.sleep(_TICK_EVERY if active else 5.0)


def stop_loop() -> None:
    global _running
    _running = False
