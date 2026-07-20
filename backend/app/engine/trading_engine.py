from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Awaitable, Callable

from app.brokers.market_data import MarketDataSimulator
from app.brokers.mt_bridge import resolve_mt_bridge
from app.brokers.paper import PaperBroker
from app.core.config import Settings
from app.engine.candles import CandleAggregator
from app.engine.trade_journal import TradeJournal
from app.models.domain import (
    AccountSnapshot,
    EngineStatus,
    Order,
    OrderRequest,
    OrderStatus,
    Position,
    PositionStatus,
    Side,
    Signal,
    Tick,
)
from app.risk.manager import RiskManager
from app.strategies import Strategy, create_strategy


Listener = Callable[[dict[str, Any]], Awaitable[None] | None]


class TradingEngine:
    """Orchestrates market data → strategy → risk → paper/MT broker + candles."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.paper = PaperBroker(settings.initial_balance, settings.base_currency)
        self.broker = self.paper  # compat for older callers
        self.risk = RiskManager(settings)
        self.market = MarketDataSimulator(settings.symbols)
        self.strategy: Strategy = create_strategy(settings.default_strategy)
        self.candles = CandleAggregator(
            period_seconds=settings.candle_period_seconds,
            maxlen=settings.candle_history,
        )
        self.journal = TradeJournal(maxlen=500)
        self.mt, detected = resolve_mt_bridge(settings)
        self.mode = settings.execution_mode if settings.execution_mode in {"paper", "mt4", "mt5"} else "paper"
        self.running = False
        self.ticks_processed = 0
        self.last_tick_at = None
        self._started_at: float | None = None
        self._task: asyncio.Task | None = None
        self._listeners: list[Listener] = []
        self._recent_signals: deque[Signal] = deque(maxlen=100)
        self._recent_ticks: dict[str, Tick] = {}
        self._lock = asyncio.Lock()
        self._mt_platform = detected

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

    def set_execution_mode(self, mode: str) -> None:
        mode = mode.lower().strip()
        if mode not in {"paper", "mt4", "mt5"}:
            raise ValueError("mode must be paper, mt4, or mt5")
        self.mode = mode
        self.settings.execution_mode = mode
        self.mt, self._mt_platform = resolve_mt_bridge(self.settings)

    def mt_online(self) -> bool:
        return bool(self.mt and self.mt.is_online())

    def using_mt(self) -> bool:
        return self.mode in {"mt4", "mt5"} and self.mt_online()

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

    def connection_info(self) -> dict:
        return {
            "mode": self.mode,
            "mt_configured": self.mt is not None,
            "mt_online": self.mt_online(),
            "mt_platform": self.mode if self.mode in {"mt4", "mt5"} else self._mt_platform,
            "bridge_dir": str(self.mt.bridge_dir) if self.mt else "",
            "using_live_feed": self.using_mt(),
            "candle_period_seconds": self.candles.period_seconds,
        }

    def recent_signals(self) -> list[Signal]:
        return list(self._recent_signals)

    def latest_ticks(self) -> list[Tick]:
        return list(self._recent_ticks.values())

    def candle_history(self, symbol: str | None = None, limit: int = 200) -> list:
        symbol = (symbol or self.settings.symbols[0]).upper()
        return [c.model_dump(mode="json") for c in self.candles.history(symbol, limit)]

    def trade_logs(self, limit: int = 100, *, include_rejected: bool = True) -> list:
        return [
            t.model_dump(mode="json")
            for t in self.journal.list(limit, include_rejected=include_rejected)
        ]

    def trade_summary(self) -> dict:
        return self.journal.summary()

    def _trades_payload(self) -> dict:
        return {"summary": self.trade_summary(), "trades": self.trade_logs(100)}

    async def _journal_close(self, position: Position) -> None:
        row = self.journal.record_close(position)
        if row:
            await self._emit("trade", row.model_dump(mode="json"))
            await self._emit("trades", self._trades_payload())

    async def _journal_fill(self, order: Order, position: Position | None = None) -> None:
        if order.status == OrderStatus.REJECTED:
            row = self.journal.record_order(order, mode=self.mode)
            await self._emit("trade", row.model_dump(mode="json"))
            await self._emit("trades", self._trades_payload())
            return
        if position is not None:
            row = self.journal.record_open_position(position, mode=self.mode)
        else:
            row = self.journal.record_order(order, mode=self.mode)
        await self._emit("trade", row.model_dump(mode="json"))
        await self._emit("trades", self._trades_payload())

    def _latest_open(self, symbol: str, side: Side) -> Position | None:
        opens = [p for p in self.open_positions() if p.symbol == symbol and p.side == side]
        return opens[-1] if opens else None

    def account_snapshot(self) -> AccountSnapshot:
        if self.using_mt():
            return self.mt.snapshot()
        return self.paper.snapshot()

    def open_positions(self) -> list[Position]:
        if self.using_mt():
            return self.mt.open_positions()
        return self.paper.open_positions()

    def _balance(self) -> float:
        return self.account_snapshot().balance

    async def manual_order(self, request: OrderRequest) -> Order:
        async with self._lock:
            return await self._execute(request)

    async def close_position(self, position_id: str) -> Position | None:
        async with self._lock:
            if self.using_mt():
                ack = self.mt.close_all()
                await self._emit("account", self.account_snapshot().model_dump(mode="json"))
                await self._emit(
                    "positions",
                    [p.model_dump(mode="json") for p in self.open_positions()],
                )
                if not ack.ok:
                    return None
                return Position(
                    id=position_id,
                    symbol=self.settings.symbols[0],
                    side=Side.BUY,
                    lots=0.0,
                    entry_price=0.0,
                    status=PositionStatus.CLOSED,
                    close_reason="mt_close",
                )
            closed = self.paper.close_position(position_id, reason="manual")
            if closed:
                self.risk.record_realized_pnl(closed.realized_pnl)
                await self._journal_close(closed)
                await self._emit("position_closed", closed.model_dump(mode="json"))
                await self._emit("account", self.paper.snapshot().model_dump(mode="json"))
            return closed

    async def _loop(self) -> None:
        try:
            while self.running:
                await self._tick_once()
                await asyncio.sleep(self.settings.tick_interval_seconds)
        except asyncio.CancelledError:
            raise

    async def _next_ticks(self) -> list[Tick]:
        if self.using_mt():
            tick = self.mt.read_tick()
            return [tick] if tick else []
        return self.market.next_ticks()

    async def _tick_once(self) -> None:
        async with self._lock:
            ticks = await self._next_ticks()
            for tick in ticks:
                self.ticks_processed += 1
                self.last_tick_at = tick.timestamp
                self._recent_ticks[tick.symbol] = tick

                if not self.using_mt():
                    closed = self.paper.update_tick(tick)
                    for position in closed:
                        self.risk.record_realized_pnl(position.realized_pnl)
                        await self._journal_close(position)
                        await self._emit("position_closed", position.model_dump(mode="json"))
                    self.journal.update_open_pnl(self.paper.open_positions())

                closed_candle, forming = self.candles.update(tick)
                if closed_candle is not None:
                    await self._emit("candle_closed", closed_candle.model_dump(mode="json"))
                await self._emit("candle", forming.model_dump(mode="json"))

                signal = self.strategy.on_tick(tick)
                if signal:
                    self._recent_signals.appendleft(signal)
                    await self._emit("signal", signal.model_dump(mode="json"))
                    await self._handle_signal(signal, tick)

                await self._emit("tick", tick.model_dump(mode="json"))

            await self._emit("account", self.account_snapshot().model_dump(mode="json"))
            await self._emit(
                "positions",
                [p.model_dump(mode="json") for p in self.open_positions()],
            )
            await self._emit("connection", self.connection_info())

    async def _handle_signal(self, signal: Signal, tick: Tick) -> None:
        for position in self.open_positions():
            if position.symbol == signal.symbol and position.side != signal.side:
                if self.using_mt():
                    self.mt.close_all()
                else:
                    closed = self.paper.close_position(position.id, reason="signal_reverse")
                    if closed:
                        self.risk.record_realized_pnl(closed.realized_pnl)
                        await self._journal_close(closed)
                        await self._emit("position_closed", closed.model_dump(mode="json"))

        for position in self.open_positions():
            if position.symbol == signal.symbol and position.side == signal.side:
                return

        request = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            lots=0.10,
            strategy=signal.strategy,
            comment=signal.reason[:60],
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )
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
            balance=self._balance(),
            open_positions=self.open_positions(),
            tick=tick,
        )
        if not decision.approved:
            rejected = Order(
                symbol=request.symbol,
                side=request.side,
                lots=request.lots,
                strategy=request.strategy,
                comment=request.comment,
                status=OrderStatus.REJECTED,
                reject_reason=decision.reason,
                stop_loss=request.stop_loss,
                take_profit=request.take_profit,
            )
            await self._journal_fill(rejected)
            await self._emit("order", rejected.model_dump(mode="json"))
            return rejected

        if tick is not None:
            sl, tp = self.risk.apply_default_stops(request, tick)
            request.stop_loss = request.stop_loss or sl
            request.take_profit = request.take_profit or tp

        request.lots = decision.adjusted_lots or request.lots

        if self.using_mt():
            order = self.mt.place_order(request)
            pos = self._latest_open(request.symbol, request.side) if order.status == OrderStatus.FILLED else None
            await self._journal_fill(order, pos)
        else:
            if self.mode in {"mt4", "mt5"} and not self.mt_online():
                rejected = Order(
                    symbol=request.symbol,
                    side=request.side,
                    lots=request.lots,
                    strategy=request.strategy,
                    comment=request.comment,
                    status=OrderStatus.REJECTED,
                    reject_reason=f"{self.mode.upper()} bridge offline — attach JM_Forex_Bridge EA",
                    stop_loss=request.stop_loss,
                    take_profit=request.take_profit,
                )
                await self._journal_fill(rejected)
                await self._emit("order", rejected.model_dump(mode="json"))
                return rejected
            order = self.paper.place_order(request)
            pos = None
            if order.status == OrderStatus.FILLED:
                # Match freshly opened paper position
                for p in reversed(self.paper.positions):
                    if (
                        p.status == PositionStatus.OPEN
                        and p.symbol == request.symbol
                        and p.side == request.side
                    ):
                        pos = p
                        break
            await self._journal_fill(order, pos)

        await self._emit("order", order.model_dump(mode="json"))
        await self._emit("account", self.account_snapshot().model_dump(mode="json"))
        await self._emit(
            "positions",
            [p.model_dump(mode="json") for p in self.open_positions()],
        )
        return order
