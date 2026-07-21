from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.api.deps import get_engine
from app.brokers.mt_bridge import resolve_mt_bridge
from app.core.config import get_settings
from app.models.domain import OrderRequest, Side, utcnow
from app.strategies import STRATEGY_REGISTRY, list_strategy_names
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import classify_session

router = APIRouter()


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


@router.get("/desk")
async def desk() -> dict:
    settings = get_settings()
    engine = get_engine()
    now = utcnow()
    session = classify_session(now)
    news = check_news_blackout(now)
    strategy = engine.strategy
    block = getattr(strategy, "last_block_reason", None)
    return {
        "symbol": "XAUUSD",
        "recommended_strategy": "auto_gold",
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
        "entry_rules": [
            "All strategies restored — auto picks by session",
            "Asia BEST (PH 7AM–7PM): asia_sr_scalp — M5 Support/Resistance fade",
            "Next after 7PM → Late London BEST: gold_confluence",
            "Overlap BEST: gold_atr_trend · NY BEST: gold_atr_trend / confluence",
            "London/NY chop: gold_sr_scalp · Decide on closed M5 only",
            "Asia: buy Support / sell Resistance + rejection · ~1.1R",
            "News / Friday late / off-hours → stand aside",
        ],
        "recommended_asia": "asia_sr_scalp",
        "recommended_london": "gold_confluence",
        "recommended_overlap": "gold_atr_trend",
        "recommended_ny": "gold_atr_trend",
        "recommended_sr_scalp": "gold_sr_scalp",
        "asia_desk_only": settings.asia_desk_only,
        "next_session": (engine.recommended_now() or {}).get("next_session"),
        "indicators": [
            "M5 S/R (Asia) · EMA confluence (London) · ATR trend (Overlap/NY)",
            "Asia session range high/low as major S/R",
            "M5 ADX 14 (regime switch)",
            "Structure / zone SL + R-multiple TP",
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
        "auto": "auto_gold",
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
    """Turn on auto_gold and transfer to the session-recommended strategy."""
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


@router.get("/account")
async def account() -> dict:
    return get_engine().account_snapshot().model_dump(mode="json")


@router.get("/positions")
async def positions() -> dict:
    engine = get_engine()
    open_pos = [p.model_dump(mode="json") for p in engine.open_positions()]
    all_pos = open_pos
    if hasattr(engine.paper, "all_positions"):
        all_pos = [p.model_dump(mode="json") for p in engine.paper.all_positions()]
    return {"open": open_pos, "all": all_pos}


@router.get("/orders")
async def orders() -> dict:
    return {
        "orders": [o.model_dump(mode="json") for o in get_engine().paper.recent_orders()]
    }


@router.get("/trades")
async def trades(limit: int = 100, include_rejected: bool = True) -> dict:
    engine = get_engine()
    limit = max(1, min(limit, 500))
    return {
        "summary": engine.trade_summary(),
        "trades": engine.trade_logs(limit, include_rejected=include_rejected),
    }


@router.get("/signals")
async def signals() -> dict:
    return {
        "signals": [s.model_dump(mode="json") for s in get_engine().recent_signals()]
    }


@router.get("/ticks")
async def ticks() -> dict:
    return {"ticks": [t.model_dump(mode="json") for t in get_engine().latest_ticks()]}


@router.post("/orders")
async def place_order(body: ManualOrderBody) -> dict:
    """Manual BUY/SELL. With auto_stops=true, SL/TP attach on fill."""
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
        auto_sl, auto_tp = engine.risk.stops_from_entry(
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
        )
    )
    data = order.model_dump(mode="json")
    data["auto_stops"] = body.auto_stops
    data["default_sl_pips"] = settings.default_stop_loss_pips
    data["default_tp_pips"] = settings.default_take_profit_pips
    return data


@router.post("/positions/{position_id}/close")
async def close_position(position_id: str) -> dict:
    closed = await get_engine().close_position(position_id)
    if closed is None:
        raise HTTPException(status_code=404, detail="Position not found or already closed")
    return closed.model_dump(mode="json")


@router.post("/positions/{position_id}/stops")
async def set_position_stops(position_id: str, body: PositionStopsBody) -> dict:
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
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail="Position not found, already closed, or MT modify unsupported",
        )
    return updated.model_dump(mode="json")


@router.websocket("/ws")
async def websocket_feed(ws: WebSocket) -> None:
    await ws.accept()
    engine = get_engine()

    async def listener(message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            engine.unsubscribe(listener)

    engine.subscribe(listener)
    try:
        await ws.send_json({"event": "engine", "data": engine.status().model_dump(mode="json")})
        await ws.send_json(
            {"event": "account", "data": engine.account_snapshot().model_dump(mode="json")}
        )
        await ws.send_json(
            {
                "event": "positions",
                "data": [p.model_dump(mode="json") for p in engine.open_positions()],
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
        await ws.send_json(
            {
                "event": "trades",
                "data": {
                    "summary": engine.trade_summary(),
                    "trades": engine.trade_logs(100),
                },
            }
        )
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        engine.unsubscribe(listener)
