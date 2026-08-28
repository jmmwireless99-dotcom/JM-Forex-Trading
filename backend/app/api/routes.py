from __future__ import annotations

from datetime import timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.account_deps import require_paper_account
from app.api.deps import get_engine
from app.brokers.mt_bridge import resolve_mt_bridge
from app.brokers.remote_bridge import (
    BRIDGE_FILES,
    COMMAND_FILE,
    ensure_remote_bridge_dir,
    verify_bridge_token,
)
from app.core.config import get_settings
from app.models.domain import OrderRequest, Side, utcnow
from app.paper_accounts import PaperAccount
from app.strategies import STRATEGY_REGISTRY, list_strategy_names
from app.strategies.catalog import entry_rules_short, strategy_catalog
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import classify_session

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RELEASES = _REPO_ROOT / "releases"


@router.get("/downloads/mt5-bridge")
async def downloads_mt5_bridge_index() -> dict:
    """Direct download links for XM MT5 bridge pack (Windows PC)."""
    base = "https://jmtechsolution.cloud/fx/api/downloads"
    return {
        "zip": f"{base}/mt5-bridge.zip",
        "bat": f"{base}/start-jm-mt5-agent.bat",
        "agent_py": f"{base}/jm_mt5_pc_agent.py",
        "ea_mq5": f"{base}/JM_Forex_Bridge.mq5",
        "readme": f"{base}/mt5-readme.txt",
        "account_txt": f"{base}/JM-FX-ACCOUNT.txt",
        "github_zip": (
            "https://github.com/jmmwireless99-dotcom/JM-Forex-Trading/raw/"
            "cursor/gold-symbol-mt5-c11c/releases/JM-FX-MT5-Bridge-Pack.zip"
        ),
    }


def _release_file(name: str) -> Path:
    candidates = [
        _RELEASES / "JM-FX-MT5-Bridge-Pack" / name,
        _RELEASES / name,
    ]
    mapping = {
        "mt5-bridge.zip": _RELEASES / "JM-FX-MT5-Bridge-Pack.zip",
        "start-jm-mt5-agent.bat": _RELEASES / "JM-FX-MT5-Bridge-Pack/pc-agent/start-jm-mt5-agent.bat",
        "jm_mt5_pc_agent.py": _RELEASES / "JM-FX-MT5-Bridge-Pack/pc-agent/jm_mt5_pc_agent.py",
        "JM_Forex_Bridge.mq5": _RELEASES / "JM-FX-MT5-Bridge-Pack/Experts/JM_Forex_Bridge.mq5",
        "mt5-readme.txt": _RELEASES / "JM-FX-MT5-Bridge-Pack/README.txt",
        "JM-FX-ACCOUNT.txt": _RELEASES / "JM-FX-MT5-Bridge-Pack/JM-FX-ACCOUNT.txt",
    }
    if name in mapping:
        candidates.insert(0, mapping[name])
    for path in candidates:
        if path.is_file():
            return path
    raise HTTPException(status_code=404, detail=f"Download not found: {name}")


@router.get("/downloads/mt5-bridge.zip")
async def download_mt5_bridge_zip() -> FileResponse:
    path = _release_file("mt5-bridge.zip")
    return FileResponse(path, filename="JM-FX-MT5-Bridge-Pack.zip", media_type="application/zip")


@router.get("/downloads/start-jm-mt5-agent.bat")
async def download_mt5_agent_bat() -> FileResponse:
    path = _release_file("start-jm-mt5-agent.bat")
    return FileResponse(path, filename="start-jm-mt5-agent.bat", media_type="application/octet-stream")


@router.get("/downloads/jm_mt5_pc_agent.py")
async def download_mt5_agent_py() -> FileResponse:
    path = _release_file("jm_mt5_pc_agent.py")
    return FileResponse(path, filename="jm_mt5_pc_agent.py", media_type="text/x-python")


@router.get("/downloads/JM_Forex_Bridge.mq5")
async def download_mt5_ea() -> FileResponse:
    path = _release_file("JM_Forex_Bridge.mq5")
    return FileResponse(path, filename="JM_Forex_Bridge.mq5", media_type="text/plain")


@router.get("/downloads/mt5-readme.txt")
async def download_mt5_readme() -> FileResponse:
    path = _release_file("mt5-readme.txt")
    return FileResponse(path, filename="README.txt", media_type="text/plain")


@router.get("/downloads/JM-FX-ACCOUNT.txt")
async def download_jm_account_txt() -> FileResponse:
    path = _release_file("JM-FX-ACCOUNT.txt")
    return FileResponse(path, filename="JM-FX-ACCOUNT.txt", media_type="text/plain")


class CreateAccountBody(BaseModel):
    """Create an isolated paper demo account for one client session."""

    label: str | None = None
    deposit: float | None = Field(default=None, gt=0, le=1_000_000)
    follow_auto: bool = True


class LoginAccountBody(BaseModel):
    """Sign in to an existing paper account with code + token."""

    code: str = Field(..., min_length=4, max_length=12)
    token: str = Field(..., min_length=8, max_length=128)


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
    """London session board: Asian range + window (Judas removed — stand aside)."""
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
        "strategy": None,
        "stand_aside": True,
        "windows": {
            "asia_utc": "00:00–06:00",
            "london_entry_utc": f"{LONDON_OPEN_UTC.strftime('%H:%M')}–{LONDON_ENTRY_END_UTC.strftime('%H:%M')}",
            "kill_pending_utc": PENDING_KILL_UTC.strftime("%H:%M"),
            "ph_note": "London 07–11 UTC ≈ 15:00–19:00 PH — stand aside",
        },
        "in_entry_window": snap.in_entry_window,
        "past_kill": snap.past_kill,
        "asian_range": snap.asian_range,
        "pending_note": snap.pending_note,
        "pending_orders": pending,
        "active_strategy": engine.status().active_strategy,
        "checklist": snap.checklist,
        "last_block_reason": snap.last_block,
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
    settings = get_engine().settings
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
    settings = get_engine().settings
    bridge, _ = resolve_mt_bridge(settings)
    if bridge is None:
        raise HTTPException(status_code=400, detail="MT bridge dir not configured")
    ack = bridge.ping()
    return {"ok": ack.ok, "command_id": ack.command_id, "detail": ack.detail}


class MtRemoteSyncBody(BaseModel):
    """PC agent pushes MT5 bridge files; server returns pending command CSV."""

    token: str = Field(..., min_length=8, max_length=128)
    status: str | None = None
    ticks: str | None = None
    positions: str | None = None
    ack: str | None = None


@router.post("/mt/remote/sync")
async def mt_remote_sync(body: MtRemoteSyncBody) -> dict:
    """Windows PC agent — sync jm_*.csv between MT5 Common\\Files and JM FX cloud."""
    settings = get_engine().settings
    if not settings.mt_remote_bridge:
        raise HTTPException(status_code=400, detail="Remote bridge disabled on server")
    try:
        verify_bridge_token(settings, body.token)
        root = ensure_remote_bridge_dir(settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    written: list[str] = []
    for name, content in (
        ("jm_status.csv", body.status),
        ("jm_ticks.csv", body.ticks),
        ("jm_positions.csv", body.positions),
        ("jm_ack.csv", body.ack),
    ):
        if content is not None:
            (root / name).write_text(content, encoding="utf-8")
            written.append(name)

    command_path = root / COMMAND_FILE
    command = command_path.read_text(encoding="utf-8") if command_path.exists() else ""
    engine = get_engine()
    if "jm_status.csv" in written or "jm_ticks.csv" in written:
        await engine.notify_mt_demo_sync()
    return {
        "ok": True,
        "written": written,
        "command": command,
        "bridge_dir": str(root),
    }


@router.get("/mt/remote/status")
async def mt_remote_agent_status(token: str) -> dict:
    """Health check for PC sync agent."""
    settings = get_engine().settings
    if not settings.mt_remote_bridge:
        raise HTTPException(status_code=400, detail="Remote bridge disabled")
    try:
        verify_bridge_token(settings, token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    bridge, platform = resolve_mt_bridge(settings)
    online = bool(bridge and bridge.is_online())
    return {
        "ok": True,
        "remote_bridge": True,
        "platform": platform,
        "execution_mode": settings.execution_mode,
        "mt_online": online,
        "mt5_demo_account_code": settings.mt5_demo_account_code or None,
        "mt5_demo_login": settings.mt5_demo_login or None,
        "symbol": settings.mt_symbol,
    }


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
        "recommended_london": "Stand aside",
        "recommended_overlap": "AI_ML → Liquidity_Sweep_SMC",
        "recommended_ny": "AI_ML → EMA_VWAP_Scalp",
        "recommended_sr_scalp": "AI_ML → Liquidity_Sweep_SMC",
        "asia_desk_only": settings.asia_desk_only,
        "next_session": (engine.recommended_now() or {}).get("next_session"),
        "indicators": [
            "AI & Machine Learning filter on every auto entry",
            "PH desk — 7AM–8PM EMA_RSI · 8PM–2AM SMC · 2AM–7AM EMA_RSI",
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


@router.post("/accounts/login")
async def login_account(body: LoginAccountBody) -> dict:
    """Validate account code + token (for dashboard login / account switch)."""
    engine = get_engine()
    try:
        acct = engine.accounts.require_by_code(body.code.strip(), body.token)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Account not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Invalid account token") from exc
    return {
        "ok": True,
        "account_id": acct.id,
        "account_code": acct.code,
        "account_label": acct.label,
        "follow_auto": acct.follow_auto,
        "account": engine.account_payload(acct),
        "mt5": engine.mt_demo_link_status(acct),
        "message": (
            "Login OK — DDDC3D is MT5-only; balance syncs from XM terminal when PC agent runs"
            if acct.code.upper() == (engine.settings.mt5_demo_account_code or "").upper()
            else "Login OK — save token in this browser to stay signed in"
        ),
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
