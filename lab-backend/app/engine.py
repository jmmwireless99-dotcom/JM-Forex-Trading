from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.accounts import LabAccountStore
from app.feed import SUPPORTED, fetch_quote

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
store = LabAccountStore(DATA_DIR / "lab_accounts.json")
_ticks: dict[str, dict] = {}
_running = False


def get_ticks() -> dict[str, dict]:
    return dict(_ticks)


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
            store.persist()
        except Exception as e:
            log.warning("lab tick %s: %s", sym, e)
        await asyncio.sleep(2.0)


def stop_loop() -> None:
    global _running
    _running = False
