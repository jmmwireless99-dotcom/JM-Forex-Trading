from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Callable, Awaitable

from app.brokers.market_data import MarketDataSimulator
from app.brokers.paper import PaperBroker
from app.core.config import Settings
from app.models.domain import (
    EngineStatus,
    Order,
    OrderRequest,
    Position,
    Signal,
    Tick,
)
from app.risk.manager import RiskManager
from app.strategies import Strategy, create_strategy


Listener = Callable[[dict[str, Any]], Awaitable[None] | None]


class TradingEngine:
    """Orchestrates market data → strategy → risk → paper broker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.broker = PaperBroker(settings.initial_balance, settings.base_currency)
        self.risk = RiskManager(settings)
        self.market = MarketDataSimulator(settings.symbols)
        self.strategy: Strategy = create_strategy(settings.default_strategy)
        self.running = False
        self.mode = "paper"
        self.ticks_processed = 0
        self.last_tick_at = None
        self._started_at: float | None = None
        self._task: asyncio.Task | None = None
        self._listeners: list[Listener] = []
        self._recent_signals: deque[Signal] = deque(maxlen=100)
        self._recent_ticks: dict[str, Tick] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def _emit(self, event: str, payload: Any) -> None:
        message = {"event": event, "data": payload}
        for listener in list(self._listeners):
            result = listener(message)
            if asyncio.iscoroutine(result):
                await result

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._started_at = time.time()
        self._task = asyncio.create_task(self._loop())
        await self._emit("engine", self.status().model_dump(mode="json"))

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._emit("engine", self.status().model_dump(mode="json"))

    def set_strategy(self, name: str) -> None:
        self.strategy = create_strategy(name)

    def status(self) -> EngineStatus:
        uptime = time.time() - self._started_at if self._started_at else 0.0
        return EngineStatus(
            running=self.running,
            mode=self.mode,
            active_strategy=self.strategy.name,
            symbols=self.settings.symbols,
            ticks_processed=self.ticks_processed,
            last_tick_at=self.last_tick_at,
            uptime_seconds=round(uptime, 1),
        )

    def recent_signals(self) -> list[Signal]:
        return list(self._recent_signals)

    def latest_ticks(self) -> list[Tick]:
        return list(self._recent_ticks.values())

    async def manual_order(self, request: OrderRequest) -> Order:
        async with self._lock:
            return await self._execute(request)

    async def close_position(self, position_id: str) -> Position | None:
        async with self._lock:
            closed = self.broker.close_position(position_id, reason="manual")
            if closed:
                self.risk.record_realized_pnl(closed.realized_pnl)
                await self._emit("position_closed", closed.model_dump(mode="json"))
                await self._emit("account", self.broker.snapshot().model_dump(mode="json"))
            return closed

    async def _loop(self) -> None:
        try:
            while self.running:
                await self._tick_once()
                await asyncio.sleep(self.settings.tick_interval_seconds)
        except asyncio.CancelledError:
            raise

    async def _tick_once(self) -> None:
        async with self._lock:
            ticks = self.market.next_ticks()
            for tick in ticks:
                self.ticks_processed += 1
                self.last_tick_at = tick.timestamp
                self._recent_ticks[tick.symbol] = tick
                closed = self.broker.update_tick(tick)
                for position in closed:
                    self.risk.record_realized_pnl(position.realized_pnl)
                    await self._emit("position_closed", position.model_dump(mode="json"))

                signal = self.strategy.on_tick(tick)
                if signal:
                    self._recent_signals.appendleft(signal)
                    await self._emit("signal", signal.model_dump(mode="json"))
                    await self._handle_signal(signal, tick)

                await self._emit("tick", tick.model_dump(mode="json"))

            await self._emit("account", self.broker.snapshot().model_dump(mode="json"))
            await self._emit(
                "positions",
                [p.model_dump(mode="json") for p in self.broker.open_positions()],
            )

    async def _handle_signal(self, signal: Signal, tick: Tick) -> None:
        # Close opposite exposure first
        for position in self.broker.open_positions():
            if position.symbol == signal.symbol and position.side != signal.side:
                closed = self.broker.close_position(position.id, reason="signal_reverse")
                if closed:
                    self.risk.record_realized_pnl(closed.realized_pnl)
                    await self._emit("position_closed", closed.model_dump(mode="json"))

        # Skip if already aligned
        for position in self.broker.open_positions():
            if position.symbol == signal.symbol and position.side == signal.side:
                return

        request = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            lots=0.10,
            strategy=signal.strategy,
            comment=signal.reason,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )
        # If strategy only provided pip distances, convert using risk helper
        if request.stop_loss is None and signal.stop_loss_pips and tick:
            pip = self.risk.pip_size(signal.symbol)
            entry = tick.ask if signal.side.value == "BUY" else tick.bid
            if signal.side.value == "BUY":
                request.stop_loss = entry - signal.stop_loss_pips * pip
                if signal.take_profit_pips:
                    request.take_profit = entry + signal.take_profit_pips * pip
            else:
                request.stop_loss = entry + signal.stop_loss_pips * pip
                if signal.take_profit_pips:
                    request.take_profit = entry - signal.take_profit_pips * pip
        await self._execute(request, tick=tick)

    async def _execute(self, request: OrderRequest, tick: Tick | None = None) -> Order:
        tick = tick or self._recent_ticks.get(request.symbol)
        decision = self.risk.evaluate(
            request,
            balance=self.broker.balance,
            open_positions=self.broker.open_positions(),
            tick=tick,
        )
        if not decision.approved:
            from app.models.domain import OrderStatus

            rejected = Order(
                symbol=request.symbol,
                side=request.side,
                lots=request.lots,
                strategy=request.strategy,
                comment=request.comment,
                status=OrderStatus.REJECTED,
                reject_reason=decision.reason,
            )
            await self._emit("order", rejected.model_dump(mode="json"))
            return rejected

        if tick is not None:
            sl, tp = self.risk.apply_default_stops(request, tick)
            request.stop_loss = request.stop_loss or sl
            request.take_profit = request.take_profit or tp

        request.lots = decision.adjusted_lots or request.lots
        order = self.broker.place_order(request)
        await self._emit("order", order.model_dump(mode="json"))
        await self._emit("account", self.broker.snapshot().model_dump(mode="json"))
        await self._emit(
            "positions",
            [p.model_dump(mode="json") for p in self.broker.open_positions()],
        )
        return order