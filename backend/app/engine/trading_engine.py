from __future__ import annotations

import asyncio
import math
import random
import time
from collections import deque
from datetime import timedelta
from typing import Any, Awaitable, Callable

from app.brokers.market_data import MarketDataSimulator
from app.brokers.mt_bridge import resolve_mt_bridge
from app.brokers.paper import PaperBroker
from app.core.config import Settings
from app.engine.candles import CandleAggregator
from app.engine.trade_journal import TradeJournal
from app.models.domain import (
    AccountSnapshot,
    Candle,
    EngineStatus,
    Order,
    OrderRequest,
    OrderStatus,
    Position,
    PositionStatus,
    Side,
    Signal,
    Tick,
    utcnow,
)
from app.risk.manager import RiskManager
from app.strategies import STRATEGY_REGISTRY, Strategy, create_strategy
from app.strategies.auto_router import AutoStrategyRouter


Listener = Callable[[dict[str, Any]], Awaitable[None] | None]

# Auto desk rotates gold trend + Asia range scalp — RSI/EMA stay manual-only.
_AUTO_POOL = (
    "gold_confluence",
    "gold_atr_trend",
    "asia_range_scalp",
)


class TradingEngine:
    """Orchestrates market data → strategy → risk → paper/MT broker + candles."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.paper = PaperBroker(settings.initial_balance, settings.base_currency)
        self.broker = self.paper  # compat for older callers
        self.risk = RiskManager(settings)
        self.market = MarketDataSimulator(settings.symbols)
        self.auto_router = AutoStrategyRouter(news_filter=settings.news_filter)
        requested = settings.default_strategy
        self.auto_enabled = bool(
            settings.auto_strategy or requested == AutoStrategyRouter.name
        )
        # Keep all strategies warm so auto-switching keeps indicator history.
        self._strategies: dict[str, Strategy] = {
            name: create_strategy(name, managed_by_auto=self.auto_enabled)
            for name in _AUTO_POOL
            if name in STRATEGY_REGISTRY
        }
        seed = "gold_confluence" if self.auto_enabled else requested
        if seed not in self._strategies:
            self._strategies[seed] = create_strategy(seed)
        self.active_name = seed
        self.strategy: Strategy = self._strategies[seed]
        # Chart TF (M1) vs decision TF (M5) — entries only on signal bar close.
        self.candles = CandleAggregator(
            period_seconds=settings.candle_period_seconds,
            maxlen=settings.candle_history,
        )
        self.signal_candles = CandleAggregator(
            period_seconds=settings.signal_period_seconds,
            maxlen=max(settings.candle_history, 120),
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
        self._last_auto_key: str | None = None
        self._last_strategy_switch_at: float = 0.0
        self._entry_cooldown_until: float = 0.0

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

    def _seed_candle_history(self) -> None:
        """Warm M1/M5 history so EMA/ADX are ready without waiting hours."""
        if self.signal_candles.closed_history(self.settings.symbols[0], 10):
            return
        symbol = self.settings.symbols[0]
        mid = self.market.last_mids().get(symbol, 2350.0)
        now = utcnow()
        for period, agg, count in (
            (self.settings.signal_period_seconds, self.signal_candles, 90),
            (self.settings.candle_period_seconds, self.candles, 120),
        ):
            bars: list[Candle] = []
            price = mid - 8.0
            for i in range(count):
                drift = math.sin(i / 9.0) * 0.55 + 0.08
                noise = random.uniform(-0.25, 0.25)
                o = price
                c = price + drift + noise
                h = max(o, c) + abs(noise) * 0.6
                l = min(o, c) - abs(noise) * 0.6
                open_time = now - timedelta(seconds=period * (count - i))
                bars.append(
                    Candle(
                        symbol=symbol,
                        open=round(o, 2),
                        high=round(h, 2),
                        low=round(l, 2),
                        close=round(c, 2),
                        volume=float(20 + i % 7),
                        period_seconds=period,
                        open_time=open_time,
                        timestamp=open_time + timedelta(seconds=period - 1),
                        is_closed=True,
                    )
                )
                price = c
            agg.seed_history(symbol, bars)
            for strat in self._strategies.values():
                if getattr(strat, "candle_driven", False) and period == self.settings.signal_period_seconds:
                    for bar in bars:
                        strat.feed_bar(bar)

    async def start(self) -> None:
        if self.running:
            return
        self._seed_candle_history()
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
        name = (name or "").strip()
        if name.startswith("auto_gold→"):
            # UI may send display label; treat as auto mode.
            name = AutoStrategyRouter.name
        if name == AutoStrategyRouter.name or name == "auto":
            self.auto_enabled = True
            if "gold_confluence" not in self._strategies:
                self._strategies["gold_confluence"] = create_strategy(
                    "gold_confluence", managed_by_auto=True
                )
            self.active_name = "gold_confluence"
            self.strategy = self._strategies["gold_confluence"]
            # Rebuild auto pool under managed flags.
            for pool_name in _AUTO_POOL:
                self._strategies[pool_name] = create_strategy(
                    pool_name, managed_by_auto=True
                )
            self.strategy = self._strategies[self.active_name]
            self._last_strategy_switch_at = time.time()
            self._last_auto_key = None
            return

        from app.strategies import STRATEGY_REGISTRY, list_strategy_names

        if name not in STRATEGY_REGISTRY:
            raise ValueError(
                f"Unknown strategy: {name}. Available: {list_strategy_names()}"
            )
        self.auto_enabled = False
        # Manual select — fresh instance (not auto-managed session gates).
        self._strategies[name] = create_strategy(name, managed_by_auto=False)
        self.active_name = name
        self.strategy = self._strategies[name]
        self._last_strategy_switch_at = time.time()
        self._last_auto_key = None

    def status(self) -> EngineStatus:
        uptime = time.time() - self._started_at if self._started_at else 0.0
        label = (
            f"auto_gold→{self.active_name}"
            if self.auto_enabled
            else self.active_name
        )
        return EngineStatus(
            running=self.running,
            mode=self.mode,
            active_strategy=label,
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
            "signal_period_seconds": self.signal_candles.period_seconds,
            "signal_timeframe": f"M{max(1, self.signal_candles.period_seconds // 60)}",
        }

    def auto_status(self) -> dict:
        decision = self.auto_router.last_decision
        return {
            "enabled": self.auto_enabled,
            "active_strategy": self.active_name,
            "display": (
                f"auto_gold→{self.active_name}" if self.auto_enabled else self.active_name
            ),
            "decision": decision.as_dict() if decision else None,
            "schedule": self.auto_router.schedule_table(),
        }

    def _arm_entry_cooldown(self) -> None:
        self._entry_cooldown_until = time.time() + float(
            self.settings.entry_cooldown_seconds
        )

    async def _apply_auto_router(self, tick: Tick) -> bool:
        """Return True if new entries are allowed this tick."""
        if not self.auto_enabled:
            return time.time() >= self._entry_cooldown_until
        prices = self._strategies["gold_confluence"].prices(tick.symbol)
        decision = self.auto_router.decide(tick.timestamp, prices)
        now = time.time()
        key = f"{decision.strategy}:{decision.slot}:{decision.regime.value}:{decision.allow_trading}"

        if decision.allow_trading and decision.strategy:
            stick = float(self.settings.strategy_stick_seconds)
            want = decision.strategy
            # Hysteresis within same family only (don't keep London strat into Asia).
            asia_swap = (
                "asia_range_scalp" in {want, self.active_name}
                and want != self.active_name
            )
            if (
                want != self.active_name
                and not asia_swap
                and self.active_name in self._strategies
                and (now - self._last_strategy_switch_at) < stick
                and self.active_name in _AUTO_POOL
            ):
                want = self.active_name
            if want != self.active_name:
                if want not in self._strategies:
                    self._strategies[want] = create_strategy(want, managed_by_auto=True)
                self.active_name = want
                self.strategy = self._strategies[want]
                self._last_strategy_switch_at = now
            if key != self._last_auto_key:
                self._last_auto_key = key
                await self._emit("auto", self.auto_status())
                await self._emit("engine", self.status().model_dump(mode="json"))
            if now < self._entry_cooldown_until:
                return False
            return True
        if key != self._last_auto_key:
            self._last_auto_key = key
            await self._emit("auto", self.auto_status())
        return False

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
            self._arm_entry_cooldown()
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
            self._arm_entry_cooldown()
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

                closed_signal, _forming_signal = self.signal_candles.update(tick)
                signal = None
                if closed_signal is not None:
                    # Feed M5 closes into strategies — not every noisy tick.
                    for strat in self._strategies.values():
                        if getattr(strat, "candle_driven", False):
                            strat.feed_bar(closed_signal)
                        else:
                            strat.feed(tick)
                    allow_entries = await self._apply_auto_router(tick)
                    if allow_entries:
                        bars = self.signal_candles.closed_history(tick.symbol, 200)
                        if getattr(self.strategy, "candle_driven", False):
                            signal = self.strategy.on_bar(bars, tick)
                        else:
                            signal = self.strategy.evaluate(tick)
                elif not getattr(self.strategy, "candle_driven", False):
                    # Manual tick strategies (RSI/EMA) still evaluate every tick.
                    self.strategy.feed(tick)
                    allow_entries = await self._apply_auto_router(tick)
                    if allow_entries:
                        signal = self.strategy.evaluate(tick)
                else:
                    # Keep auto status fresh even between M5 closes.
                    await self._apply_auto_router(tick)

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
            if self.auto_enabled:
                await self._emit("auto", self.auto_status())

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
