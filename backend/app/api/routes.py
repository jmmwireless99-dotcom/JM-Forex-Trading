from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.api.deps import get_engine
from app.models.domain import OrderRequest, Side
from app.strategies import STRATEGY_REGISTRY

router = APIRouter()


class StartRequest(BaseModel):
    strategy: str | None = None


class StrategyRequest(BaseModel):
    name: str


class ManualOrderBody(BaseModel):
    symbol: str
    side: Side
    lots: float = Field(gt=0, le=10)
    comment: str = "manual"


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "JM Forex"}


@router.get("/status")
async def status() -> dict:
    engine = get_engine()
    return engine.status().model_dump(mode="json")


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
    return {"strategies": list(STRATEGY_REGISTRY.keys())}


@router.post("/strategies/active")
async def set_strategy(body: StrategyRequest) -> dict:
    engine = get_engine()
    try:
        engine.set_strategy(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return engine.status().model_dump(mode="json")


@router.get("/account")
async def account() -> dict:
    return get_engine().broker.snapshot().model_dump(mode="json")


@router.get("/positions")
async def positions() -> dict:
    engine = get_engine()
    return {
        "open": [p.model_dump(mode="json") for p in engine.broker.open_positions()],
        "all": [p.model_dump(mode="json") for p in engine.broker.all_positions()],
    }


@router.get("/orders")
async def orders() -> dict:
    return {
        "orders": [o.model_dump(mode="json") for o in get_engine().broker.recent_orders()]
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
    engine = get_engine()
    order = await engine.manual_order(
        OrderRequest(
            symbol=body.symbol.upper(),
            side=body.side,
            lots=body.lots,
            comment=body.comment,
            strategy="manual",
        )
    )
    return order.model_dump(mode="json")


@router.post("/positions/{position_id}/close")
async def close_position(position_id: str) -> dict:
    closed = await get_engine().close_position(position_id)
    if closed is None:
        raise HTTPException(status_code=404, detail="Position not found or already closed")
    return closed.model_dump(mode="json")


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
        # Send initial snapshot
        await ws.send_json({"event": "engine", "data": engine.status().model_dump(mode="json")})
        await ws.send_json(
            {"event": "account", "data": engine.broker.snapshot().model_dump(mode="json")}
        )
        await ws.send_json(
            {
                "event": "positions",
                "data": [p.model_dump(mode="json") for p in engine.broker.open_positions()],
            }
        )
        while True:
            # Keepalive / ignore client pings
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        engine.unsubscribe(listener)