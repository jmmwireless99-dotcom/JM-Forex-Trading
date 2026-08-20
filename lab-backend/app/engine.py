from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from app.accounts import LabAccountStore
from app.auto import try_auto_fill
from app.feed import SUPPORTED, fetch_candles, fetch_quote

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
store = LabAccountStore(DATA_DIR / "lab_accounts.json")
_ticks: dict[str, dict] = {}
_running = False
_candle_cache: dict[str, tuple[float, list]] = {}
_AUTO_CHECK_EVERY = 60.0


def get_ticks() -> dict[str, dict]:
    return dict(_ticks)


def _auto_symbols() -> set[str]:
    out: set[str] = set()
    for acc in store.all_accounts():
        if acc.auto.enabled:
            out.add(acc.auto.symbol.upper())
    return out


async def _maybe_run_auto(sym: str, mid: float) -> None:
    if not any(a.auto.enabled and a.auto.symbol.upper() == sym for a in store.all_accounts()):
        return
    now = time.monotonic()
    cached = _candle_cache.get(sym)
    if cached and now - cached[0] < _AUTO_CHECK_EVERY:
        candles = cached[1]
    else:
        try:
            payload = await asyncio.to_thread(fetch_candles, sym, interval="5", limit=120)
            candles = payload.get("candles") or []
            _candle_cache[sym] = (now, candles)
        except Exception as e:
            log.warning("lab auto candles %s: %s", sym, e)
            return

    changed = False
    for acc in store.all_accounts():
        if not acc.auto.enabled or acc.auto.symbol.upper() != sym:
            continue
        acc.broker.update_tick(sym, mid)
        if try_auto_fill(acc, candles, mid):
            changed = True
    if changed:
        store.persist()


async def tick_loop() -> None:
    global _running
    _running = True
    idx = 0
    while _running:
        sym = SUPPORTED[idx % len(SUPPORTED)]
        idx += 1
        try:
            q = await asyncio.to_thread(fetch_quote, sym)
            _ticks[sym] = q
            for acc in store.all_accounts():
                acc.broker.update_tick(sym, q["mid"])
            await _maybe_run_auto(sym, q["mid"])
            store.persist()
        except Exception as e:
            log.warning("lab tick %s: %s", sym, e)
        await asyncio.sleep(5.0)


def stop_loop() -> None:
    global _running
    _running = False
