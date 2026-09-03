from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
import logging

from app.engine import get_ticks, store
from app.feed import SUPPORTED, fetch_candles, fetch_quote, fetch_quote_live
from app.pair_strategies import PAIR_PRESETS, STRATEGIES, preset_for, strategy_info

log = logging.getLogger(__name__)

router = APIRouter()


class CreateAccountBody(BaseModel):
    deposit: float = Field(10_000.0, ge=50, le=1_000_000)
    label: str = Field("Lab demo", max_length=80)


class PairSuiteBody(BaseModel):
    deposit: float = Field(10_000.0, ge=50, le=1_000_000)
    start_auto: bool = True


class OrderBody(BaseModel):
    symbol: str = "EURUSD"
    side: str  # BUY | SELL
    lots: float = Field(0.01, ge=0.01, le=50)
    stop_loss: float | None = None
    take_profit: float | None = None


class AutoBody(BaseModel):
    enabled: bool | None = None
    symbol: str | None = None
    lots: float | None = Field(None, ge=0.01, le=50)
    sl_pips: float | None = Field(None, ge=1, le=500)
    tp_pips: float | None = Field(None, ge=1, le=500)
    strategy: str | None = None


def _auth(account_id: str | None, token: str | None):
    if not account_id:
        raise HTTPException(400, "Missing X-JM-Lab-Account-Id")
    try:
        return store.auth(account_id, token)
    except PermissionError as e:
        raise HTTPException(401, str(e)) from e


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "JM Lab Trading", "symbols": SUPPORTED}


@router.get("/symbols")
async def symbols() -> dict:
    return {"symbols": SUPPORTED}


@router.get("/quote")
async def quote(symbol: str = "EURUSD", fresh: bool = False) -> dict:
    sym = symbol.upper()
    if sym not in SUPPORTED:
        raise HTTPException(400, f"Unsupported symbol: {sym}")
    try:
        q = fetch_quote_live(sym) if fresh else fetch_quote(sym)
    except Exception as e:
        log.warning("quote %s fresh=%s: %s", sym, fresh, e)
        cached = get_ticks().get(sym)
        if cached:
            return {**cached, "stale": True}
        raise HTTPException(503, "Live quote unavailable") from e
    return q


@router.get("/ticks")
async def ticks(symbol: str | None = None, fresh: bool = False) -> dict:
    sym = symbol.upper() if symbol else None
    if sym and sym not in SUPPORTED:
        raise HTTPException(400, f"Unsupported symbol: {symbol}")
    live = get_ticks()
    if sym:
        if fresh:
            try:
                row = fetch_quote_live(sym)
            except Exception as e:
                row = live.get(sym)
                if not row:
                    raise HTTPException(503, "Live quote unavailable") from e
                row = {**row, "stale": True}
            return {"tick": row}
        row = live.get(sym)
        if not row:
            try:
                row = fetch_quote(sym)
            except Exception as e:
                raise HTTPException(503, "Live quote unavailable") from e
        return {"tick": row}
    if not live:
        # cold start
        out = {}
        for s in SUPPORTED:
            try:
                out[s] = fetch_quote(s)
            except Exception:
                pass
        return {"ticks": out}
    return {"ticks": live}


@router.get("/strategies")
async def list_strategies() -> dict:
    pairs = {sym: preset_for(sym) for sym in SUPPORTED}
    return {"strategies": STRATEGIES, "pair_presets": pairs}


@router.get("/candles")
async def candles(symbol: str = "EURUSD", interval: str = "5", limit: int = 120) -> dict:
    try:
        return fetch_candles(symbol, interval=interval, limit=min(limit, 500))
    except Exception as e:
        log.warning("candles %s: %s", symbol, e)
        raise HTTPException(503, "Chart data temporarily unavailable — retry in a minute") from e


@router.post("/accounts")
async def create_account(body: CreateAccountBody) -> dict:
    acc = store.create(deposit=body.deposit, label=body.label)
    return {
        "ok": True,
        "account": acc.snapshot(),
        "token": acc.token,
        "message": f"Lab demo account {acc.code} created with ${body.deposit:,.2f}",
    }


@router.post("/accounts/pair-suite")
async def create_pair_suite(body: PairSuiteBody) -> dict:
    """One account per pair (EURUSD, GBPUSD, AUDNZD, EURCHF) for parallel dry-run."""
    rows = store.bootstrap_pair_suite(deposit=body.deposit, start_auto=body.start_auto)
    accounts = []
    for row in rows:
        acc = store.get(row["account_id"])
        if acc:
            accounts.append({**row, "account": acc.snapshot(), "pair_preset": preset_for(row["symbol"])})
    return {
        "ok": True,
        "message": f"Pair suite ready — {len(accounts)} accounts (one per pair)",
        "accounts": accounts,
    }


@router.get("/account")
async def get_account(
    x_jm_lab_account_id: str | None = Header(None),
    x_jm_lab_account_token: str | None = Header(None),
) -> dict:
    acc = _auth(x_jm_lab_account_id, x_jm_lab_account_token)
    tick = get_ticks().get("EURUSD")
    if tick:
        acc.broker.update_tick("EURUSD", tick["mid"])
    return acc.snapshot()


@router.get("/positions")
async def positions(
    x_jm_lab_account_id: str | None = Header(None),
    x_jm_lab_account_token: str | None = Header(None),
) -> dict:
    acc = _auth(x_jm_lab_account_id, x_jm_lab_account_token)
    for sym, t in get_ticks().items():
        acc.broker.update_tick(sym, t["mid"])
    open_rows = [p.to_dict() for p in acc.broker.open_positions()]
    return {"positions": open_rows}


@router.get("/trades")
async def trades(
    x_jm_lab_account_id: str | None = Header(None),
    x_jm_lab_account_token: str | None = Header(None),
) -> dict:
    acc = _auth(x_jm_lab_account_id, x_jm_lab_account_token)
    return {"trades": acc.broker.trades[:100]}


@router.post("/orders/market")
async def market_order(
    body: OrderBody,
    x_jm_lab_account_id: str | None = Header(None),
    x_jm_lab_account_token: str | None = Header(None),
) -> dict:
    acc = _auth(x_jm_lab_account_id, x_jm_lab_account_token)
    sym = body.symbol.upper()
    if sym not in SUPPORTED:
        raise HTTPException(400, f"Unsupported symbol: {sym}")
    side = body.side.upper()
    if side not in {"BUY", "SELL"}:
        raise HTTPException(400, "side must be BUY or SELL")
    ticks = get_ticks()
    if sym not in ticks:
        try:
            q = fetch_quote(sym)
            ticks[sym] = q
            acc.broker.update_tick(sym, q["mid"])
        except Exception as e:
            raise HTTPException(502, str(e)) from e
    else:
        acc.broker.update_tick(sym, ticks[sym]["mid"])
    try:
        pos = acc.broker.open_market(
            symbol=sym,
            side=side,  # type: ignore[arg-type]
            lots=body.lots,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    store.persist()
    return {"ok": True, "position": pos.to_dict(), "account": acc.snapshot()}


@router.post("/positions/{position_id}/close")
async def close_position(
    position_id: str,
    x_jm_lab_account_id: str | None = Header(None),
    x_jm_lab_account_token: str | None = Header(None),
) -> dict:
    acc = _auth(x_jm_lab_account_id, x_jm_lab_account_token)
    for sym, t in get_ticks().items():
        acc.broker.update_tick(sym, t["mid"])
    closed = acc.broker.close_position(position_id, reason="manual")
    if closed is None:
        raise HTTPException(404, "Position not found")
    store.persist()
    return {"ok": True, "position": closed.to_dict(), "account": acc.snapshot()}


@router.get("/auto")
async def get_auto(
    x_jm_lab_account_id: str | None = Header(None),
    x_jm_lab_account_token: str | None = Header(None),
) -> dict:
    acc = _auth(x_jm_lab_account_id, x_jm_lab_account_token)
    a = acc.auto
    info = strategy_info(a.strategy)
    return {
        "enabled": a.enabled,
        "symbol": a.symbol,
        "lots": a.lots,
        "sl_pips": a.sl_pips,
        "tp_pips": a.tp_pips,
        "strategy": a.strategy,
        "strategy_name": info.get("name"),
        "strategy_description": info.get("description"),
        "pair_preset": preset_for(a.symbol),
        "last_signal_at": a.last_signal_at,
        "last_block_reason": a.last_block_reason,
        "recent_signals": list(a.signals),
    }


@router.post("/auto")
async def set_auto(
    body: AutoBody,
    x_jm_lab_account_id: str | None = Header(None),
    x_jm_lab_account_token: str | None = Header(None),
) -> dict:
    acc = _auth(x_jm_lab_account_id, x_jm_lab_account_token)
    a = acc.auto
    if body.enabled is not None:
        a.enabled = body.enabled
    if body.symbol is not None:
        sym = body.symbol.upper()
        if sym not in SUPPORTED:
            raise HTTPException(400, f"Unsupported symbol: {sym}")
        a.symbol = sym
        # Apply pair-specific strategy preset when symbol changes
        p = preset_for(sym)
        a.strategy = p["strategy"]
        if body.lots is None:
            a.lots = p["lots"]
        if body.sl_pips is None:
            a.sl_pips = p["sl_pips"]
        if body.tp_pips is None:
            a.tp_pips = p["tp_pips"]
        a.last_bar_time = 0
    if body.lots is not None:
        a.lots = body.lots
    if body.sl_pips is not None:
        a.sl_pips = body.sl_pips
    if body.tp_pips is not None:
        a.tp_pips = body.tp_pips
    if body.strategy:
        a.strategy = body.strategy.upper()
    info = strategy_info(a.strategy)
    store.persist()
    return {
        "ok": True,
        "auto": acc.auto.to_dict(),
        "strategy_info": info,
        "pair_preset": preset_for(a.symbol),
        "account": acc.snapshot(),
    }
