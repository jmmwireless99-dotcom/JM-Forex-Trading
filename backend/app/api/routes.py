from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.api.account_deps import require_paper_account
from app.api.deps import get_engine
from app.brokers.mt_bridge import resolve_mt_bridge
from app.core.config import get_settings
from app.models.domain import OrderRequest, Side, utcnow
from app.paper_accounts import PaperAccount
from app.strategies import STRATEGY_REGISTRY, list_strategy_names
from app.strategies.catalog import entry_rules_short, strategy_catalog
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import classify_session

router = APIRouter()


class CreateAccountBody(BaseModel):
    """Create an isolated paper demo account for one client session."""

    label: str | None = None
    deposit: float | None = Field(default=None, gt=0, le=1_000_000)
    follow_auto: bool = True


class StartRequest(BaseModel):
    strategy: str | None = None


class StrategyRequest(BaseModel):
    name: str


class ExecutionModeBody(BaseModel):
    mode: str  # paper | mt4 | mt5


class ManualOrderBody(BaseModel):
    symbol: str = "XAUUSD"
    side: Side
    lots: float = Field(default=0.01, gt=0, le=10)
    comment: str = "manual"
    # Auto-attach desk default SL/TP right after fill (or use pips below)
    auto_stops: bool = True
    stop_loss: float | None = None
    take_profit: float | None = None
    stop_loss_pips: float | None = Field(default=None, gt=0, le=500)
    take_profit_pips: float | None = Field(default=None, gt=0, le=1000)


class DepositBody(BaseModel):
    """Paper demo deposit / starting capital for client trials."""

    amount: float = Field(..., gt=0, le=1_000_000)
    reset: bool = True  # close opens + clear paper trade log


class PositionStopsBody(BaseModel):
    """Set SL/TP on an open position. auto=True uses desk default pip distances."""

    stop_loss: float | None = None
    take_profit: float | None = None
    auto: bool = False
    stop_loss_pips: float | None = Field(default=None, gt=0, le=500)
    take_profit_pips: float | None = Field(default=None, gt=0, le=1000)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "JM Forex"}


@router.get("/db/health")
async def db_health() -> dict:
    from app.db.session import ping_db

    return ping_db()


@router.get("/db/strategies")
async def db_strategies(active_only: bool = False) -> dict:
    from app.db.repository import list_strategies
    from app.db.session import db_enabled

    if not db_enabled():
        return {"ok": False, "configured": False, "strategies": []}
    rows = list_strategies(active_only=active_only)
    return {"ok": True, "configured": True, "strategies": rows}


@router.get("/london")
async def london_desk() -> dict:
    """London Judas session board: Asian range + window + pending kill."""
    from app.engine.london_engine import LondonEngine
    from app.strategies.london_session import (
        LONDON_ENTRY_END_UTC,
        LONDON_OPEN_UTC,
        PENDING_KILL_UTC,
    )

    engine = get_engine()
    bars = engine.signal_candles.closed_history(engine.settings.symbols[0], 240)
    ts = engine.last_tick_at or utcnow()
    snap = LondonEngine().snapshot(bars, ts)
    pending = []
    if not engine.using_mt():
        pending = [o.model_dump(mode="json") for o in engine.paper.pending_orders()]
    return {
        "ok": True,
        "strategy": "London_Judas_Sweep",
        "windows": {
            "asia_utc": "00:00–06:00",
            "london_entry_utc": f"{LONDON_OPEN_UTC.strftime('%H:%M')}–{LONDON_ENTRY_END_UTC.strftime('%H:%M')}",
            "kill_pending_utc": PENDING_KILL_UTC.strftime("%H:%M"),
            "ph_note": "London 07–16 UTC ≈ 15:00–00:00 PH",
        },
        "in_entry_window": snap.in_entry_window,
        "past_kill": snap.past_kill,
        "asian_range": snap.asian_range,
        "pending_note": snap.pending_note,
        "pending_orders": pending,
        "active_strategy": engine.status().active_strategy,
        "checklist": getattr(engine.strategy, "last_checklist", []),
        "last_block_reason": getattr(engine.strategy, "last_block_reason", None),
    }


@router.post("/db/seed")
async def db_seed() -> dict:
    from app.db.seed import seed_strategies
    from app.db.session import db_enabled

    if not db_enabled():
        raise HTTPException(status_code=400, detail="JM_DATABASE_URL not set")
    return seed_strategies(force_update=True)


@router.get("/status")
async def status() -> dict:
    engine = get_engine()
    data = engine.status().model_dump(mode="json")
    data["connection"] = engine.connection_info()
    return data


@router.get("/mt/status")
@router.get("/mt4/status")
async def mt_status() -> dict:
    settings = get_settings()
    engine = get_engine()
    bridge, platform = resolve_mt_bridge(settings)
    info = engine.connection_info()
    if bridge is None:
        return {
            "configured": False,
            "online": False,
            "execution_mode": settings.execution_mode,
            "platform": platform,
            "bridge_dir": "",
            "hint": "Set JM_MT4_BRIDGE_DIR or JM_MT5_BRIDGE_DIR to Terminal Common\\Files",
            **info,
        }
    online = bridge.is_online()
    tick = bridge.read_tick() if online else None
    snap = bridge.snapshot() if online else None
    return {
        "configured": True,
        "online": online,
        "execution_mode": settings.execution_mode,
        "platform": info.get("mt_platform") or platform,
        "bridge_dir": str(bridge.bridge_dir),
        "symbol": bridge.symbol,
        "tick": tick.model_dump(mode="json") if tick else None,
        "account": snap.model_dump(mode="json") if snap else None,
        "positions": [p.model_dump(mode="json") for p in bridge.open_positions()] if online else [],
        **info,
    }


@router.post("/mt/ping")
@router.post("/mt4/ping")
async def mt_ping() -> dict:
    settings = get_settings()
    bridge, _ = resolve_mt_bridge(settings)
    if bridge is None:
        raise HTTPException(status_code=400, detail="MT bridge dir not configured")
    ack = bridge.ping()
    return {"ok": ack.ok, "command_id": ack.command_id, "detail": ack.detail}


@router.post("/execution/mode")
async def set_execution_mode(body: ExecutionModeBody) -> dict:
    engine = get_engine()
    try:
        engine.set_execution_mode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **engine.connection_info(), "status": engine.status().model_dump(mode="json")}


@router.get("/candles")
async def candles(symbol: str | None = None, limit: int = 200) -> dict:
    engine = get_engine()
    limit = max(10, min(limit, 500))
    return {
        "symbol": (symbol or engine.settings.symbols[0]).upper(),
        "period_seconds": engine.candles.period_seconds,
        "candles": engine.candle_history(symbol, limit),
    }


@router.get("/market/gold-candles")
async def gold_candles(interval: str = "5m", limit: int = 300) -> dict:
    """Live gold OHLC for dashboard (Yahoo GC=F). Display only — not strategy feed."""
    from app.market_data.gold_feed import fetch_gold_candles

    try:
        return fetch_gold_candles(interval=interval, limit=min(max(limit, 50), 1000))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/desk")
async def desk() -> dict:
    """Clean slate desk board — session/news/risk only; no auto strategies."""
    settings = get_settings()
    engine = get_engine()
    now = utcnow()
    session = classify_session(now)
    news = check_news_blackout(now)
    strategy = engine.strategy
    block = getattr(strategy, "last_block_reason", None)
    return {
        "symbol": "XAUUSD",
        "mode": "scalp_desk",
        "recommended_strategy": "AI_ML",
        "recommended_now": engine.recommended_now(),
        "active_strategy": engine.status().active_strategy,
        "auto": engine.auto_status(),
        "connection": engine.connection_info(),
        "session": {
            "tier": session.tier.value,
            "label": session.label,
            "reason": session.reason,
            "filter_enabled": settings.session_filter,
            "prime_only": settings.prime_session_only,
        },
        "news": {
            "blocked": news.blocked,
            "event": news.event,
            "reason": news.reason,
            "filter_enabled": settings.news_filter,
        },
        "signal_timeframe": f"M{max(1, settings.signal_period_seconds // 60)}",
        "chart_timeframe": f"M{max(1, settings.candle_period_seconds // 60)}",
        "entry_rules": entry_rules_short(),
        "strategy_details": strategy_catalog(),
        "recommended_asia": "AI_ML → EMA_RSI_Scalp",
        "recommended_london": "AI_ML → London_Judas_Sweep",
        "recommended_overlap": "AI_ML → Liquidity_Sweep_SMC",
        "recommended_ny": "AI_ML → EMA_VWAP_Scalp",
        "recommended_sr_scalp": "AI_ML → Liquidity_Sweep_SMC",
        "asia_desk_only": settings.asia_desk_only,
        "next_session": (engine.recommended_now() or {}).get("next_session"),
        "indicators": [
            "AI & Machine Learning filter on every auto entry",
            "London Judas: Asian High/Low + ChoCH + FVG 50% limit",
            "EMA 200 / 20 / 50 + RSI 14",
            "Engulfing + pin bar confirmation",
            "Spread > 30 pips ($0.30) blocked · UK/EUR news −15m",
        ],
        "entry_checklist": getattr(strategy, "last_checklist", []),
        "asia_range": getattr(strategy, "last_range", None),
        "sr_zones": getattr(strategy, "last_zones", None),
        "risk": {
            "max_risk_per_trade_pct": settings.max_risk_per_trade_pct,
            "max_open_positions": settings.max_open_positions,
            "max_daily_loss_pct": settings.max_daily_loss_pct,
        },
        "last_block_reason": block,
        "server_time_utc": now.astimezone(timezone.utc).isoformat(),
        "ai": engine.ai_status(),
    }


@router.post("/engine/start")
async def start_engine(body: StartRequest | None = None) -> dict:
    engine = get_engine()
    if body and body.strategy:
        try:
            engine.set_strategy(body.strategy)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await engine.start()
    return engine.status().model_dump(mode="json")


@router.post("/engine/stop")
async def stop_engine() -> dict:
    engine = get_engine()
    await engine.stop()
    return engine.status().model_dump(mode="json")


@router.get("/strategies")
async def list_strategies() -> dict:
    return {
        "strategies": list_strategy_names(),
        "auto": None,
        "pool": list(STRATEGY_REGISTRY.keys()),
    }


@router.get("/auto")
async def auto_status() -> dict:
    return get_engine().auto_status()


@router.get("/strategies/recommended")
async def recommended_strategy() -> dict:
    """Recommended strategy for the current session time (+ regime)."""
    return get_engine().recommended_now()


@router.post("/strategies/auto-transfer")
async def auto_transfer_strategy() -> dict:
    """Clean slate — no auto strategies to transfer to."""
    engine = get_engine()
    return await engine.auto_transfer(start_engine=True)


@router.post("/strategies/active")
async def set_strategy(body: StrategyRequest) -> dict:
    engine = get_engine()
    try:
        engine.set_strategy(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = engine.status().model_dump(mode="json")
    await engine._emit("engine", status)
    await engine._emit("auto", engine.auto_status())
    return {
        **status,
        "ok": True,
        "selected": body.name,
        "auto": engine.auto_status(),
    }


@router.post("/accounts")
async def create_account(body: CreateAccountBody | None = None) -> dict:
    """Create a private paper account — capital/trades/history isolated per client."""
    body = body or CreateAccountBody()
    return get_engine().create_client_account(
        label=body.label,
        deposit=body.deposit,
        follow_auto=body.follow_auto,
    )


@router.get("/accounts/me")
async def account_me(account: PaperAccount = Depends(require_paper_account)) -> dict:
    """Return the caller's private account (requires X-JM-Account-Id + token)."""
    engine = get_engine()
    return {
        **engine.account_payload(account),
        "capital": engine.capital_preview(account=account),
        "trades": engine._trades_payload(account),
    }


@router.get("/account")
async def account(account: PaperAccount = Depends(require_paper_account)) -> dict:
    engine = get_engine()
    return {
        **engine.account_payload(account),
        "capital": engine.capital_preview(account=account),
    }


@router.get("/account/capital")
async def capital_preview(
    amount: float | None = None,
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    """Preview risk sizing for a deposit amount without applying it."""
    return get_engine().capital_preview(amount, account=account)


@router.post("/account/deposit")
async def set_deposit(
    body: DepositBody,
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    """Set paper demo deposit on the caller's account only."""
    engine = get_engine()
    try:
        return await engine.set_paper_deposit(
            body.amount, reset=body.reset, account=account
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/positions")
async def positions(account: PaperAccount = Depends(require_paper_account)) -> dict:
    engine = get_engine()
    open_pos = [p.model_dump(mode="json") for p in engine.open_positions(account)]
    all_pos = [p.model_dump(mode="json") for p in account.broker.all_positions()]
    return {"account_id": account.id, "open": open_pos, "all": all_pos}


@router.get("/orders")
async def orders(account: PaperAccount = Depends(require_paper_account)) -> dict:
    return {
        "account_id": account.id,
        "orders": [o.model_dump(mode="json") for o in account.broker.recent_orders()],
    }


@router.get("/trades")
async def trades(
    limit: int = 100,
    include_rejected: bool = True,
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    engine = get_engine()
    limit = max(1, min(limit, 500))
    return {
        "account_id": account.id,
        "summary": engine.trade_summary(account),
        "trades": engine.trade_logs(
            limit, include_rejected=include_rejected, account=account
        ),
    }


@router.post("/trades/clear")
async def clear_trades(
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    """Clear this account's trade log and reset daily risk counters."""
    return await get_engine().clear_trade_log(account)


@router.get("/signals")
async def signals() -> dict:
    return {
        "signals": [s.model_dump(mode="json") for s in get_engine().recent_signals()]
    }


@router.get("/ai/status")
async def ai_status() -> dict:
    """AI & Machine Learning status — history, sklearn metrics, last advice."""
    return get_engine().ai_status()


@router.get("/ai/advice")
async def ai_advice(
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    """Score the latest signal with AI & Machine Learning."""
    return get_engine().ai_advice(account)


@router.get("/ai/history")
async def ai_history(limit: int = 50) -> dict:
    """Persisted Machine Learning feature history (opens + labeled closes)."""
    return get_engine().ai_history(limit)


@router.post("/ai/retrain")
async def ai_retrain(
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    """Backfill journal labels and retrain the Machine Learning model."""
    return get_engine().ai_retrain(account)


@router.get("/ticks")
async def ticks() -> dict:
    return {"ticks": [t.model_dump(mode="json") for t in get_engine().latest_ticks()]}


@router.post("/orders")
async def place_order(
    body: ManualOrderBody,
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    """Manual BUY/SELL on the caller's paper account only."""
    engine = get_engine()
    settings = get_settings()
    symbol = (body.symbol or "XAUUSD").upper()
    sl = body.stop_loss
    tp = body.take_profit
    tick = engine._recent_ticks.get(symbol)
    if body.auto_stops and tick is not None and (
        body.stop_loss_pips is not None or body.take_profit_pips is not None
    ):
        entry = tick.ask if body.side == Side.BUY else tick.bid
        auto_sl, auto_tp = account.risk.stops_from_entry(
            symbol=symbol,
            side=body.side,
            entry=entry,
            stop_loss_pips=body.stop_loss_pips,
            take_profit_pips=body.take_profit_pips,
        )
        sl = sl if sl is not None else auto_sl
        tp = tp if tp is not None else auto_tp
    order = await engine.manual_order(
        OrderRequest(
            symbol=symbol,
            side=body.side,
            lots=body.lots,
            comment=body.comment,
            strategy="manual",
            stop_loss=sl,
            take_profit=tp,
            attach_stops=body.auto_stops,
        ),
        account=account,
    )
    data = order.model_dump(mode="json")
    data["account_id"] = account.id
    data["auto_stops"] = body.auto_stops
    data["default_sl_pips"] = settings.default_stop_loss_pips
    data["default_tp_pips"] = settings.default_take_profit_pips
    return data


@router.post("/positions/{position_id}/close")
async def close_position(
    position_id: str,
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    closed = await get_engine().close_position(position_id, account=account)
    if closed is None:
        raise HTTPException(status_code=404, detail="Position not found or already closed")
    return {**closed.model_dump(mode="json"), "account_id": account.id}


@router.post("/positions/{position_id}/stops")
async def set_position_stops(
    position_id: str,
    body: PositionStopsBody,
    account: PaperAccount = Depends(require_paper_account),
) -> dict:
    """Attach / update SL & TP after a manual (or any) open."""
    if not body.auto and body.stop_loss is None and body.take_profit is None:
        raise HTTPException(
            status_code=400,
            detail="Provide stop_loss/take_profit or set auto=true",
        )
    updated = await get_engine().set_position_stops(
        position_id,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        auto=body.auto
        or body.stop_loss_pips is not None
        or body.take_profit_pips is not None,
        stop_loss_pips=body.stop_loss_pips,
        take_profit_pips=body.take_profit_pips,
        account=account,
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail="Position not found, already closed, or MT modify unsupported",
        )
    return {**updated.model_dump(mode="json"), "account_id": account.id}


@router.websocket("/ws")
async def websocket_feed(ws: WebSocket) -> None:
    await ws.accept()
    engine = get_engine()
    account_id = ws.query_params.get("account_id")
    account_token = ws.query_params.get("account_token")
    account: PaperAccount | None = None
    if account_id:
        try:
            account = engine.accounts.require(account_id, account_token)
        except (KeyError, PermissionError):
            account = None

    def _for_account(payload: object) -> bool:
        """Drop money/trade events that belong to another client account."""
        if account is None:
            # Shared market feed only when no account bound
            return True
        if not isinstance(payload, dict):
            return True
        aid = payload.get("account_id")
        if aid is None:
            return True
        return aid == account.id

    async def listener(message: dict) -> None:
        try:
            event = message.get("event")
            if event in {
                "account",
                "positions",
                "trades",
                "trade",
                "order",
                "position",
                "position_closed",
            } and not _for_account(message.get("data")):
                return
            await ws.send_json(message)
        except Exception:
            engine.unsubscribe(listener)

    engine.subscribe(listener)
    if account is not None:
        engine.register_connected_account(account)
    try:
        await ws.send_json({"event": "engine", "data": engine.status().model_dump(mode="json")})
        if account is not None:
            await ws.send_json(
                {"event": "account", "data": engine.account_payload(account)}
            )
            await ws.send_json(
                {
                    "event": "positions",
                    "data": {
                        "account_id": account.id,
                        "positions": [
                            p.model_dump(mode="json")
                            for p in engine.open_positions(account)
                        ],
                    },
                }
            )
            await ws.send_json(
                {
                    "event": "trades",
                    "data": engine._trades_payload(account),
                }
            )
        await ws.send_json({"event": "connection", "data": engine.connection_info()})
        await ws.send_json({"event": "auto", "data": engine.auto_status()})
        await ws.send_json(
            {
                "event": "candles",
                "data": {
                    "period_seconds": engine.candles.period_seconds,
                    "candles": engine.candle_history(limit=200),
                },
            }
        )
        # Desk-wide signal tape — same for every browser/account (not filtered).
        await ws.send_json(
            {
                "event": "signals",
                "data": {
                    "signals": [
                        s.model_dump(mode="json") for s in engine.recent_signals()
                    ]
                },
            }
        )
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if account is not None:
            engine.unregister_connected_account(account.id)
        engine.unsubscribe(listener)
