from __future__ import annotations

import asyncio
import math
import random
import time
from collections import deque
from datetime import timedelta
from typing import Any, Awaitable, Callable

from app.ai.advisor import TradeAdvisor
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
    OrderType,
    Position,
    PositionStatus,
    Side,
    Signal,
    Tick,
    utcnow,
)
from app.paper_accounts import PaperAccount, PaperAccountRegistry
from app.risk.manager import RiskManager
from app.strategies import STRATEGY_REGISTRY, Strategy, create_strategy
from app.strategies.auto_router import AutoStrategyRouter


Listener = Callable[[dict[str, Any]], Awaitable[None] | None]

# Session-follow pool for auto transfer by time.
_AUTO_POOL = (
    "AI_ML",
    "EMA_RSI_Scalp",
    "London_Judas_Sweep",
    "Liquidity_Sweep_SMC",
    "EMA_VWAP_Scalp",
)


class TradingEngine:
    """Orchestrates market data → strategy → risk → paper/MT broker + candles."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Isolated paper books — each client account has own capital + trade log
        self.accounts = PaperAccountRegistry(settings)
        # Internal desk book for engine helpers / MT fallback — never exposed to clients.
        # Client/API traffic must use account-scoped methods.
        self._desk = self.accounts.ensure_desk(settings.initial_balance)
        self.paper = self._desk.broker
        self.broker = self.paper
        self.risk = self._desk.risk
        self.journal = self._desk.journal
        self.market = MarketDataSimulator(
            settings.symbols,
            live_noise=settings.paper_live_noise,
        )
        if settings.paper_sync_live_gold and settings.execution_mode == "paper":
            self.market.set_live_mid_provider(self._live_gold_mid)
        self.auto_router = AutoStrategyRouter(news_filter=settings.news_filter)
        requested = settings.default_strategy or "manual_only"
        if requested not in STRATEGY_REGISTRY:
            requested = "manual_only"
        self.auto_enabled = bool(settings.auto_strategy)
        self._strategies: dict[str, Strategy] = {
            "manual_only": create_strategy("manual_only"),
        }
        if requested != "manual_only" and requested in STRATEGY_REGISTRY:
            self._strategies[requested] = create_strategy(requested)
        self.active_name = requested if requested in self._strategies else "manual_only"
        self.strategy: Strategy = self._strategies[self.active_name]
        # Chart TF (M1) · signal TF (M5)
        self.candles = CandleAggregator(
            period_seconds=settings.candle_period_seconds,
            maxlen=settings.candle_history,
        )
        self.signal_candles = CandleAggregator(
            period_seconds=settings.signal_period_seconds,
            maxlen=max(settings.candle_history, 260),
        )
        self.m3_candles = CandleAggregator(
            period_seconds=180,
            maxlen=max(settings.candle_history, 200),
        )
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
        self._last_session_slot: str | None = None
        self._last_transfer_note: str | None = None
        self._journaled_limit_ids: set[str] = set()
        self._london_signal_ids: dict[str, str] = {}  # order.id -> london_signal uuid
        self.advisor = TradeAdvisor(
            history_path=settings.ai_history_path,
            model_path=settings.ai_model_path,
            enabled=settings.ai_assist,
            gate_entries=settings.ai_gate_entries,
            min_win_prob=settings.ai_min_win_prob,
            skip_confidence=settings.ai_skip_confidence,
            block_smc_sell_overlap=settings.ai_block_smc_sell_overlap,
            smc_sell_overlap_min_wr=settings.ai_smc_sell_overlap_min_wr,
            smc_sell_overlap_min_n=settings.ai_smc_sell_overlap_min_n,
        )
        self._last_advice: dict[str, Any] | None = None
        # Bind AI & ML into any strategies that support it (esp. AI_ML).
        for strat in self._strategies.values():
            self._bind_advisor(strat)

    def _bind_advisor(self, strategy: Strategy | None) -> None:
        if strategy is not None and hasattr(strategy, "set_advisor"):
            strategy.set_advisor(self.advisor)

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def create_client_account(
        self,
        *,
        label: str | None = None,
        deposit: float | None = None,
        follow_auto: bool = True,
    ) -> dict[str, Any]:
        """Provision an isolated paper account for one client browser/session."""
        acct = self.accounts.create(
            deposit=deposit,
            label=label,
            follow_auto=follow_auto,
            is_desk=False,
        )
        return {
            "ok": True,
            "account": acct.snapshot_payload(),
            "token": acct.token,
            "capital": self.capital_preview(acct.broker.deposit, account=acct),
            "trades": self._trades_payload(acct),
            "message": (
                "New demo account created. Only this account id + token can see "
                "its capital, trades, and history."
            ),
        }

    def account_snapshot(self, account: PaperAccount | None = None) -> AccountSnapshot:
        if account is None and self.using_mt():
            return self.mt.snapshot()
        acct = account or self._desk
        return acct.broker.snapshot()

    def account_payload(self, account: PaperAccount | None = None) -> dict[str, Any]:
        acct = account or self._desk
        if account is None and self.using_mt():
            snap = self.mt.snapshot().model_dump(mode="json")
            return {**snap, "account_id": None, "account_code": None}
        return acct.snapshot_payload()

    def trade_logs(
        self,
        limit: int = 100,
        *,
        include_rejected: bool = True,
        account: PaperAccount | None = None,
    ) -> list:
        acct = account or self._desk
        return [
            t.model_dump(mode="json")
            for t in acct.journal.list(limit, include_rejected=include_rejected)
        ]

    def trade_summary(self, account: PaperAccount | None = None) -> dict:
        acct = account or self._desk
        return acct.journal.summary()

    def _trades_payload(self, account: PaperAccount | None = None) -> dict:
        acct = account or self._desk
        return {
            "account_id": acct.id,
            "summary": self.trade_summary(acct),
            "trades": self.trade_logs(100, account=acct),
        }

    def open_positions(self, account: PaperAccount | None = None) -> list[Position]:
        if account is None and self.using_mt():
            return self.mt.open_positions()
        acct = account or self._desk
        return acct.broker.open_positions()

    def _balance(self, account: PaperAccount | None = None) -> float:
        return self.account_snapshot(account).balance

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
        if mode == "paper" and self.settings.paper_sync_live_gold:
            self.market.set_live_mid_provider(self._live_gold_mid)
        else:
            self.market.set_live_mid_provider(None)

    def mt_online(self) -> bool:
        return bool(self.mt and self.mt.is_online())

    def using_mt(self) -> bool:
        return self.mode in {"mt4", "mt5"} and self.mt_online()

    def _live_gold_mid(self, symbol: str) -> float | None:
        """Live gold mid for paper desk sync (display + paper fills near TV)."""
        if (symbol or "").upper() != "XAUUSD":
            return None
        try:
            from app.market_data.gold_feed import fetch_gold_candles

            data = fetch_gold_candles(interval="5m", limit=5)
            price = data.get("price")
            if price is None and data.get("candles"):
                price = data["candles"][-1].get("close")
            return float(price) if price is not None else None
        except Exception:
            return None

    def _seed_candle_history(self) -> None:
        """Warm M1/M5 history so EMA/ADX are ready without waiting hours."""
        if self.signal_candles.closed_history(self.settings.symbols[0], 10):
            return
        # Pin paper mid to live gold BEFORE seeding so EMA history sits near TV price.
        if self.settings.paper_sync_live_gold and self.settings.execution_mode == "paper":
            self.market.pull_live_mids(force=True)
        symbol = self.settings.symbols[0]
        mid = self.market.last_mids().get(symbol, 2350.0)
        now = utcnow()
        # EMA200 needs 205+ M5 closes — seed past that so Asia/EMA can fire after restart.
        signal_seed = max(220, int(self.settings.candle_history))
        last_close = mid
        for period, agg, count in (
            (self.settings.signal_period_seconds, self.signal_candles, signal_seed),
            (180, self.m3_candles, max(160, signal_seed // 2)),
            (self.settings.candle_period_seconds, self.candles, signal_seed),
        ):
            bars: list[Candle] = []
            # Oscillate around the live mid so EMA20/200 stay near current tape
            price = mid
            for i in range(count):
                # Mean-revert to mid — last bars finish at the live price
                target = mid + math.sin(i / 11.0) * 1.2
                # Stronger pull on the final 30 bars so seed end ≈ live mid
                if i >= count - 30:
                    target = mid + math.sin(i / 7.0) * 0.25
                delta = (target - price) * 0.35 + random.uniform(-0.12, 0.12)
                o = price
                c = price + delta
                h = max(o, c) + abs(delta) * 0.35 + 0.05
                l = min(o, c) - abs(delta) * 0.35 - 0.05
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
            last_close = price
            agg.seed_history(symbol, bars)
            for strat in self._strategies.values():
                if getattr(strat, "candle_driven", False) and period == self.settings.signal_period_seconds:
                    for bar in bars:
                        strat.feed_bar(bar)
        # Keep the live simulator glued to the seeded close (EMA proximity)
        self.market.sync_mid(symbol, last_close)

    async def start(self) -> None:
        if self.running:
            return
        self._seed_candle_history()
        if self.auto_enabled:
            rec = self.recommended_now()
            target = rec.get("transfer_to") or rec.get("strategy")
            note = f"Boot session auto-follow ({rec.get('session')})"
            if not target:
                target, note = self._stand_aside_park_target(utcnow())
            if target and target in STRATEGY_REGISTRY:
                self._park_strategy(target, note=note)
                self._last_session_slot = rec.get("session")
        self.running = True
        self._started_at = time.time()
        self._task = asyncio.create_task(self._loop())
        await self._emit("engine", self.status().model_dump(mode="json"))
        if self.auto_enabled:
            await self._emit("auto", self.auto_status())

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
        if name.startswith("auto_gold") or name in {"auto", AutoStrategyRouter.name}:
            self.auto_enabled = True
            rec = self.recommended_now()
            target = rec.get("transfer_to") or rec.get("strategy") or "manual_only"
            if target not in STRATEGY_REGISTRY:
                target = "manual_only"
            self._strategies[target] = create_strategy(target)
            self._bind_advisor(self._strategies[target])
            self.active_name = target
            self.strategy = self._strategies[target]
            self._last_strategy_switch_at = time.time()
            self._last_auto_key = None
            self._last_session_slot = rec.get("session")
            self._last_transfer_note = f"Auto transfer -> {target}"
            return

        from app.strategies import STRATEGY_REGISTRY, list_strategy_names

        if name not in STRATEGY_REGISTRY:
            raise ValueError(
                f"Unknown strategy: {name}. Available: {list_strategy_names()}"
            )
        self.auto_enabled = False
        self._strategies[name] = create_strategy(name)
        self._bind_advisor(self._strategies[name])
        self.active_name = name
        self.strategy = self._strategies[name]
        self._last_strategy_switch_at = time.time()
        self._last_auto_key = None

    def status(self) -> EngineStatus:
        uptime = time.time() - self._started_at if self._started_at else 0.0
        return EngineStatus(
            running=self.running,
            mode=self.mode,
            active_strategy=self.active_name,
            symbols=self.settings.symbols,
            ticks_processed=self.ticks_processed,
            last_tick_at=self.last_tick_at,
            uptime_seconds=round(uptime, 1),
        )

    def connection_info(self) -> dict:
        mids = self.market.last_mids()
        return {
            "mode": self.mode,
            "mt_configured": self.mt is not None,
            "mt_online": self.mt_online(),
            "mt_platform": self.mode if self.mode in {"mt4", "mt5"} else self._mt_platform,
            "bridge_dir": str(self.mt.bridge_dir) if self.mt else "",
            "using_live_feed": self.using_mt(),
            "paper_sync_live_gold": bool(
                self.settings.paper_sync_live_gold and self.mode == "paper"
            ),
            "paper_mid": mids.get(self.settings.symbols[0]),
            "candle_period_seconds": self.candles.period_seconds,
            "signal_period_seconds": self.signal_candles.period_seconds,
            "signal_timeframe": f"M{max(1, self.signal_candles.period_seconds // 60)}",
        }

    def _signal_prices(self, symbol: str | None = None) -> list[float]:
        symbol = (symbol or self.settings.symbols[0]).upper()
        bars = self.signal_candles.closed_history(symbol, 240)
        if bars:
            return [c.close for c in bars]
        return self.strategy.prices(symbol)

    def recommended_now(self) -> dict:
        """Session clock + recommended session strategy."""
        ts = self.last_tick_at or utcnow()
        prices = self._signal_prices()
        rec = self.auto_router.recommend(ts, prices)
        child = rec.get("child_strategy")
        display = self.active_name
        if (self.active_name == "AI_ML" or rec.get("strategy") == "AI_ML") and child:
            display = f"AI_ML → {child}"
        return {
            **rec,
            "auto_enabled": self.auto_enabled,
            "current_strategy": self.active_name,
            "display": display,
        }

    def auto_status(self) -> dict:
        decision = self.auto_router.last_decision
        rec = self.recommended_now()
        child = decision.child_strategy if decision is not None else None
        if self.active_name == "AI_ML" and hasattr(self.strategy, "active_child_name"):
            child = getattr(self.strategy, "active_child_name", None) or child
        display = (
            f"AI_ML → {child}"
            if self.active_name == "AI_ML" and child
            else self.active_name
        )
        return {
            "enabled": self.auto_enabled,
            "session_follow": self.auto_enabled,
            "active_strategy": self.active_name,
            "child_strategy": child,
            "display": display,
            "session_slot": self._last_session_slot,
            "last_transfer": self._last_transfer_note,
            "decision": decision.as_dict() if decision else None,
            "recommended": rec,
            "schedule": self.auto_router.schedule_table(),
            "ai_ml": True,
        }

    def _park_strategy(self, name: str, *, note: str) -> bool:
        """Switch active strategy. Returns True if changed."""
        if not name:
            return False
        if name not in self._strategies:
            if name not in STRATEGY_REGISTRY:
                return False
            self._strategies[name] = create_strategy(name)
        self._bind_advisor(self._strategies[name])
        if name == self.active_name:
            return False
        self.active_name = name
        self.strategy = self._strategies[name]
        self._last_strategy_switch_at = time.time()
        self._last_transfer_note = note
        return True

    def _stand_aside_park_target(self, ts) -> tuple[str, str]:
        """During avoid slots, arm the next session strategy (not idle manual)."""
        from app.strategies.session import next_session_hint

        nxt = next_session_hint(ts)
        target = nxt.get("strategy")
        if target and target in STRATEGY_REGISTRY:
            hour = nxt.get("hour_utc")
            slot = nxt.get("session")
            note = f"Stand aside now — armed {target} for {slot} @ {hour}:00 UTC"
            return target, note
        return "manual_only", "Stand aside — no tradeable session soon"

    async def auto_transfer(self, *, start_engine: bool = True) -> dict:
        """Enable session-follow and transfer to current (or next) recommended strategy."""
        self.auto_enabled = True
        rec = self.recommended_now()
        target = rec.get("transfer_to") or rec.get("strategy")
        note = f"Auto session transfer ({rec.get('session')})"
        stand_aside = False
        if not target:
            stand_aside = True
            ts = self.last_tick_at or utcnow()
            target, note = self._stand_aside_park_target(ts)
            rec = {
                **rec,
                "armed_for_next": True,
                "transfer_to": target if target != "manual_only" else None,
                "stand_aside_note": note,
            }
        switched = False
        previous = self.active_name
        if target and target in STRATEGY_REGISTRY:
            switched = self._park_strategy(target, note=note)
            self._last_session_slot = rec.get("session")
        if start_engine and not self.running:
            await self.start()
        status = self.status().model_dump(mode="json")
        auto = self.auto_status()
        await self._emit("engine", status)
        await self._emit("auto", auto)
        if stand_aside and target != "manual_only":
            message = (
                f"Kill/stand-aside hour — auto ON, armed {target} for next session "
                f"(no new entries until then)"
            )
        elif stand_aside:
            message = "Stand aside — auto ON, waiting for next tradeable session"
        elif switched:
            message = f"Session-follow: {previous} → {self.active_name}"
        else:
            message = f"Session-follow active: stay on {self.active_name}"
        return {
            "ok": True,
            "transferred": switched,
            "auto_enabled": self.auto_enabled,
            "from": previous,
            "to": self.active_name,
            "recommended": rec,
            "status": status,
            "auto": auto,
            "message": message,
            "stand_aside": stand_aside,
            **status,
        }

    def _arm_entry_cooldown(self) -> None:
        self._entry_cooldown_until = time.time() + float(
            self.settings.entry_cooldown_seconds
        )

    async def _london_kill_switch(self, tick: Tick) -> None:
        from app.strategies.london_session import is_past_pending_kill

        if self.using_mt() or not is_past_pending_kill(tick.timestamp):
            return
        for acct in self.accounts.all():
            cancelled = acct.broker.cancel_pending(
                reason="London kill switch 12:00 UTC — unfilled limit cancelled"
            )
            for order in cancelled:
                lid = self._london_signal_ids.get(f"{acct.id}:{order.id}")
                if lid:
                    try:
                        from app.db.repository import mark_london_signal

                        mark_london_signal(lid, status="CANCELLED")
                    except Exception:
                        pass
                await self._emit(
                    "order",
                    {**order.model_dump(mode="json"), "account_id": acct.id},
                )

    async def _sync_limit_fills(self, account: PaperAccount) -> None:
        """Journal LIMIT orders that filled on tick (pending → filled)."""
        for order in account.broker.orders:
            key = f"{account.id}:{order.id}"
            if (
                order.order_type == OrderType.LIMIT
                and order.status == OrderStatus.FILLED
                and key not in self._journaled_limit_ids
            ):
                pos = self._latest_open(order.symbol, order.side, account)
                await self._journal_fill(
                    order,
                    pos,
                    signal_db_id=None,
                    account=account,
                )
                self._journaled_limit_ids.add(key)
                lid = self._london_signal_ids.get(key)
                if lid:
                    try:
                        from app.db.repository import mark_london_signal
                        from app.models.domain import utcnow as _utcnow

                        mark_london_signal(
                            lid, status="EXECUTED", execution_timestamp=_utcnow()
                        )
                    except Exception:
                        pass
                await self._emit(
                    "order",
                    {**order.model_dump(mode="json"), "account_id": account.id},
                )

    async def _persist_london(self, signal: Signal) -> str | None:
        try:
            from app.db.repository import create_london_signal, upsert_london_range
            from app.db.session import db_enabled
            from app.strategies.london_session import calculate_asian_range

            if not db_enabled() or signal.strategy != "London_Judas_Sweep":
                return None
            bars = self.signal_candles.closed_history(signal.symbol, 240)
            asian = calculate_asian_range(bars, as_of=signal.timestamp)
            session_id = None
            if asian:
                swept_h = signal.side.value == "SELL"
                swept_l = signal.side.value == "BUY"
                session_id = upsert_london_range(
                    session_date=asian.session_date,
                    asian_high=asian.high,
                    asian_low=asian.low,
                    asian_range_pips=asian.range_pips,
                    is_swept_high=swept_h,
                    is_swept_low=swept_l,
                )
            entry = signal.limit_price or 0
            risk = abs((signal.stop_loss or 0) - entry)
            reward = abs(entry - (signal.take_profit or 0))
            rr = round(reward / risk, 3) if risk else None
            return create_london_signal(
                session_id=session_id,
                signal_type=signal.side.value,
                sweep_price=float(signal.sweep_price or entry),
                entry_price=float(entry),
                stop_loss=float(signal.stop_loss or 0),
                take_profit=float(signal.take_profit or 0),
                risk_reward_ratio=rr,
                metadata={"reason": signal.reason},
            )
        except Exception:
            return None

    async def _persist_candle(self, candle: Candle, *, timeframe: str) -> None:
        try:
            from app.db.repository import upsert_candle
            from app.db.session import db_enabled

            if not db_enabled():
                return
            upsert_candle(
                symbol=candle.symbol,
                timeframe=timeframe,
                timestamp=candle.open_time or candle.timestamp,
                open_=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=int(candle.volume or 0),
            )
        except Exception:
            pass

    async def _persist_signal(self, signal: Signal) -> str | None:
        try:
            from app.db.repository import create_signal
            from app.db.session import db_enabled

            if not db_enabled():
                return None
            if signal.stop_loss is None or signal.take_profit is None:
                return None
            entry = (
                self._recent_ticks.get(signal.symbol).mid
                if signal.symbol in self._recent_ticks
                else signal.stop_loss
            )
            tick = self._recent_ticks.get(signal.symbol)
            if tick:
                entry = tick.ask if signal.side.value == "BUY" else tick.bid
            return create_signal(
                strategy_name=signal.strategy,
                symbol=signal.symbol,
                signal_type=signal.side.value,
                entry_price=float(entry),
                stop_loss=float(signal.stop_loss),
                take_profit=float(signal.take_profit),
                timeframe="M5",
                metadata={"reason": signal.reason, "strength": signal.strength},
            )
        except Exception:
            return None

    async def _persist_trade_open(
        self, order: Order, position: Position | None, *, signal_db_id: str | None
    ) -> None:
        try:
            from app.db.repository import create_trade
            from app.db.session import db_enabled

            if not db_enabled() or order.status != OrderStatus.FILLED:
                return
            create_trade(
                symbol=order.symbol,
                order_type=order.side.value,
                lot_size=order.lots,
                open_price=float(order.fill_price or 0),
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                signal_id=signal_db_id,
                strategy_name=order.strategy,
                ticket=position.id if position else order.id,
                mode=self.mode,
                metadata={"comment": order.comment},
            )
        except Exception:
            pass

    async def _persist_trade_close(self, position: Position) -> None:
        try:
            from app.db.repository import close_trade
            from app.db.session import db_enabled

            if not db_enabled():
                return
            reason = (position.close_reason or "").lower()
            status = "CLOSED_MANUAL"
            if "tp" in reason or "take" in reason:
                status = "CLOSED_TP"
            elif "sl" in reason or "stop" in reason:
                status = "CLOSED_SL"
            close_trade(
                ticket=position.id,
                close_price=float(position.close_price or 0),
                pnl_amount=float(position.realized_pnl),
                status=status,
            )
            # Persist SMC zones snapshot if present
            zones = getattr(self.strategy, "last_zones", None)
            if zones:
                from app.db.repository import upsert_zone

                for z in zones[:8]:
                    upsert_zone(
                        symbol=position.symbol,
                        zone_type=z.get("zone_type", "FVG"),
                        price_high=float(z["price_high"]),
                        price_low=float(z["price_low"]),
                        metadata={"is_swept": z.get("is_swept", False)},
                    )
        except Exception:
            pass

    async def _apply_auto_router(self, tick: Tick) -> bool:
        """Apply session-follow transfer and decide if entries are allowed."""
        prices = self._signal_prices(tick.symbol)
        decision = self.auto_router.decide(tick.timestamp, prices)

        if self.auto_enabled and decision.strategy:
            switched = self._park_strategy(
                decision.strategy, note=f"Session auto-follow ({decision.slot})"
            )
            if switched:
                self._last_session_slot = decision.slot
                await self._emit("engine", self.status().model_dump(mode="json"))
                await self._emit("auto", self.auto_status())
        elif self.auto_enabled and not decision.allow_trading:
            # Stand-aside: arm next session strategy (entries still blocked)
            park, note = self._stand_aside_park_target(tick.timestamp)
            if self.active_name != park:
                switched = self._park_strategy(park, note=note)
                if switched:
                    self._last_session_slot = decision.slot
                    await self._emit("engine", self.status().model_dump(mode="json"))
                    await self._emit("auto", self.auto_status())

        if self.active_name == "manual_only":
            return False
        if time.time() < self._entry_cooldown_until:
            return False
        if self.auto_enabled and not decision.allow_trading:
            return False
        return getattr(self.strategy, "candle_driven", False) or self.active_name in STRATEGY_REGISTRY

    def recent_signals(self) -> list[Signal]:
        return list(self._recent_signals)

    def ai_status(self) -> dict[str, Any]:
        payload = self.advisor.status()
        payload["last_advice"] = self._last_advice
        return payload

    def ai_advice(self, account: PaperAccount | None = None) -> dict[str, Any]:
        """Score the newest signal; optionally backfill journal history first."""
        acct = account or self._desk
        if self.advisor.enabled:
            try:
                self.advisor.ingest_closed_trades(
                    acct.journal.list(500, include_rejected=False),
                    account_id=acct.id,
                )
            except Exception:
                pass
        signals = list(self._recent_signals)
        if not signals:
            return {
                "ok": True,
                "advice": None,
                "message": "No recent signals to score",
                "status": self.ai_status(),
            }
        signal = signals[0]
        tick = self._recent_ticks.get(signal.symbol)
        entry = None
        if tick is not None:
            entry = tick.ask if signal.side == Side.BUY else tick.bid
        if signal.limit_price is not None:
            entry = signal.limit_price
        advice = self.advisor.advise_signal(signal, entry=entry)
        self._last_advice = advice.as_dict()
        return {
            "ok": True,
            "advice": self._last_advice,
            "signal": signal.model_dump(mode="json"),
            "status": self.ai_status(),
        }

    def ai_history(self, limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        return {
            "events": self.advisor.store.recent(limit),
            "stats": self.advisor.store.stats(),
        }

    def ai_retrain(self, account: PaperAccount | None = None) -> dict[str, Any]:
        acct = account or self._desk
        ingested = self.advisor.ingest_closed_trades(
            acct.journal.list(500, include_rejected=False),
            account_id=acct.id,
        )
        result = self.advisor.retrain()
        result["ingested_from_journal"] = ingested
        result["status"] = self.ai_status()
        return result

    def latest_ticks(self) -> list[Tick]:
        return list(self._recent_ticks.values())

    def candle_history(self, symbol: str | None = None, limit: int = 200) -> list:
        symbol = (symbol or self.settings.symbols[0]).upper()
        return [c.model_dump(mode="json") for c in self.candles.history(symbol, limit)]

    async def _journal_close(self, position: Position, account: PaperAccount) -> None:
        row = account.journal.record_close(position)
        if row:
            self._arm_entry_cooldown()
            await self._persist_trade_close(position)
            if self.advisor.enabled:
                try:
                    self.advisor.record_close_from_trade(row)
                    await self._emit("ai", self.ai_status())
                except Exception:
                    pass
            payload = {**row.model_dump(mode="json"), "account_id": account.id}
            await self._emit("trade", payload)
            await self._emit("trades", self._trades_payload(account))

    async def _journal_fill(
        self,
        order: Order,
        position: Position | None = None,
        *,
        signal_db_id: str | None = None,
        account: PaperAccount | None = None,
    ) -> None:
        acct = account or self._desk
        order_payload = {**order.model_dump(mode="json"), "account_id": acct.id}
        if order.status == OrderStatus.PENDING:
            await self._emit("order", order_payload)
            return
        if order.status == OrderStatus.REJECTED:
            row = acct.journal.record_order(order, mode=self.mode)
            await self._emit("trade", {**row.model_dump(mode="json"), "account_id": acct.id})
            await self._emit("trades", self._trades_payload(acct))
            return
        if position is not None:
            row = acct.journal.record_open_position(position, mode=self.mode)
            self._arm_entry_cooldown()
            await self._persist_trade_open(order, position, signal_db_id=signal_db_id)
            if self.advisor.enabled:
                try:
                    self.advisor.record_open_from_trade(
                        row, account_id=acct.id, mode=self.mode
                    )
                except Exception:
                    pass
        else:
            row = acct.journal.record_order(order, mode=self.mode)
        await self._emit("trade", {**row.model_dump(mode="json"), "account_id": acct.id})
        await self._emit("trades", self._trades_payload(acct))

    def _latest_open(self, symbol: str, side: Side, account: PaperAccount | None = None) -> Position | None:
        opens = [p for p in self.open_positions(account) if p.symbol == symbol and p.side == side]
        return opens[-1] if opens else None

    def capital_preview(
        self,
        deposit: float | None = None,
        account: PaperAccount | None = None,
    ) -> dict:
        """Show how risk / lot sizing scales with a paper deposit amount."""
        acct = account or self._desk
        amount = float(deposit if deposit is not None else acct.broker.deposit)
        risk_pct = float(self.settings.max_risk_per_trade_pct)
        daily_pct = float(self.settings.max_daily_loss_pct)
        stop_pips = float(self.settings.default_stop_loss_pips)
        tp_pips = float(self.settings.default_take_profit_pips)
        risk_usd = amount * (risk_pct / 100.0)
        daily_usd = amount * (daily_pct / 100.0) if daily_pct > 0 else None
        pip_value_per_lot = 10.0  # XAUUSD desk convention in RiskManager
        suggested = risk_usd / (stop_pips * pip_value_per_lot) if stop_pips > 0 else 0.01
        suggested_lots = max(0.01, round(suggested, 2))
        return {
            "deposit": round(amount, 2),
            "currency": self.settings.base_currency,
            "paper": not self.using_mt(),
            "risk_per_trade_pct": risk_pct,
            "risk_per_trade_usd": round(risk_usd, 2),
            "max_daily_loss_pct": daily_pct,
            "max_daily_loss_usd": round(daily_usd, 2) if daily_usd is not None else None,
            "daily_loss_limit_enabled": daily_pct > 0,
            "default_stop_loss_pips": stop_pips,
            "default_take_profit_pips": tp_pips,
            "suggested_lots": suggested_lots,
            "account_id": acct.id,
            "presets": [100, 250, 500, 1000, 2500, 5000, 10000, 25000],
            "note": "Paper demo capital for this account only — other clients cannot see it",
        }

    async def set_paper_deposit(
        self,
        amount: float,
        *,
        reset: bool = True,
        account: PaperAccount | None = None,
    ) -> dict:
        """Set fake deposit / starting capital for one paper account.

        Trade log history is always kept. When reset=True, open positions are
        closed (and journaled) then balance is set to the new deposit.
        """
        acct = account or self._desk
        if self.using_mt():
            raise ValueError("Deposit amount is paper-only. Switch execution mode to paper first.")
        async with self._lock:
            closed = acct.broker.set_deposit(float(amount), close_positions=reset)
            for position in closed:
                await self._journal_close(position, acct)
            acct.risk.reset_daily(acct.broker.balance)
            # Keep trade log history — do not clear journal
            self.accounts.save()
            snap = acct.snapshot_payload()
            capital = self.capital_preview(account=acct)
            await self._emit("account", snap)
            await self._emit("trades", self._trades_payload(acct))
            return {
                "ok": True,
                "account": snap,
                "capital": capital,
                "trades": self._trades_payload(acct),
                "message": (
                    f"Paper deposit set to ${capital['deposit']:,.2f} on {acct.code} "
                    f"(trade history kept · {acct.journal.summary()['total']} logged)"
                ),
            }

    async def clear_trade_log(self, account: PaperAccount | None = None) -> dict:
        """Wipe trade journal for one account and reset daily risk counters."""
        acct = account or self._desk
        async with self._lock:
            if not self.using_mt():
                for position in list(acct.broker.open_positions()):
                    closed = acct.broker.close_position(position.id, reason="log_clear")
                    if closed:
                        acct.risk.record_realized_pnl(closed.realized_pnl)
                acct.broker.cancel_pending(reason="Cancelled — trade log cleared")
            acct.journal.clear()
            snap = acct.broker.snapshot()
            acct.risk.reset_daily(snap.equity)
            self.accounts.save()
            payload = self._trades_payload(acct)
            await self._emit("trades", payload)
            await self._emit("account", self.account_payload(acct))
            await self._emit(
                "positions",
                {
                    "account_id": acct.id,
                    "positions": [
                        p.model_dump(mode="json") for p in self.open_positions(acct)
                    ],
                },
            )
            return {
                "ok": True,
                "account": self.account_payload(acct),
                "trades": payload,
                "message": f"Trade log cleared for account {acct.code}",
            }

    async def manual_order(
        self, request: OrderRequest, account: PaperAccount | None = None
    ) -> Order:
        async with self._lock:
            return await self._execute(request, account=account)

    async def set_position_stops(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        auto: bool = False,
        stop_loss_pips: float | None = None,
        take_profit_pips: float | None = None,
        account: PaperAccount | None = None,
    ) -> Position | None:
        """Attach / update SL & TP on an open position (manual desk helper)."""
        acct = account or self._desk
        async with self._lock:
            if self.using_mt():
                return None  # MT modify not supported via file bridge yet
            pos = next(
                (p for p in acct.broker.open_positions() if p.id == position_id),
                None,
            )
            if pos is None:
                return None
            sl = stop_loss
            tp = take_profit
            if auto or (sl is None and tp is None):
                auto_sl, auto_tp = acct.risk.stops_from_entry(
                    symbol=pos.symbol,
                    side=pos.side,
                    entry=pos.entry_price,
                    stop_loss_pips=stop_loss_pips,
                    take_profit_pips=take_profit_pips,
                )
                if sl is None:
                    sl = auto_sl
                if tp is None:
                    tp = auto_tp
            updated = acct.broker.set_stops(
                position_id, stop_loss=sl, take_profit=tp
            )
            if updated:
                acct.journal.update_open_pnl(acct.broker.open_positions())
                await self._emit(
                    "position",
                    {**updated.model_dump(mode="json"), "account_id": acct.id},
                )
                await self._emit(
                    "positions",
                    {
                        "account_id": acct.id,
                        "positions": [
                            p.model_dump(mode="json") for p in self.open_positions(acct)
                        ],
                    },
                )
            return updated

    async def close_position(
        self, position_id: str, account: PaperAccount | None = None
    ) -> Position | None:
        acct = account or self._desk
        async with self._lock:
            if self.using_mt():
                ack = self.mt.close_all()
                await self._emit("account", self.account_payload(acct))
                await self._emit(
                    "positions",
                    {
                        "account_id": acct.id,
                        "positions": [
                            p.model_dump(mode="json") for p in self.open_positions(acct)
                        ],
                    },
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
            closed = acct.broker.close_position(position_id, reason="manual")
            if closed:
                acct.risk.record_realized_pnl(closed.realized_pnl)
                await self._journal_close(closed, acct)
                await self._emit(
                    "position_closed",
                    {**closed.model_dump(mode="json"), "account_id": acct.id},
                )
                await self._emit("account", self.account_payload(acct))
                self.accounts.save()
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
                    for acct in self.accounts.all():
                        closed = acct.broker.update_tick(tick)
                        for position in closed:
                            acct.risk.record_realized_pnl(position.realized_pnl)
                            await self._journal_close(position, acct)
                            await self._emit(
                                "position_closed",
                                {
                                    **position.model_dump(mode="json"),
                                    "account_id": acct.id,
                                },
                            )
                        acct.journal.update_open_pnl(acct.broker.open_positions())
                        await self._sync_limit_fills(acct)
                    await self._london_kill_switch(tick)

                closed_candle, forming = self.candles.update(tick)
                if closed_candle is not None:
                    await self._emit("candle_closed", closed_candle.model_dump(mode="json"))
                await self._emit("candle", forming.model_dump(mode="json"))

                closed_signal, _forming_signal = self.signal_candles.update(tick)
                closed_m3, _forming_m3 = self.m3_candles.update(tick)
                signal = None
                uses_m3_entry = (
                    getattr(self.strategy, "entry_period_seconds", None) == 180
                )

                if closed_signal is not None:
                    # Feed M5 closes into strategies — structure / standard entries.
                    await self._persist_candle(closed_signal, timeframe="M5")
                    for strat in self._strategies.values():
                        if getattr(strat, "candle_driven", False):
                            strat.feed_bar(closed_signal)
                            if hasattr(strat, "set_structure_bars"):
                                strat.set_structure_bars(
                                    self.signal_candles.closed_history(tick.symbol, 240)
                                )
                            if hasattr(strat, "set_m1_bars"):
                                strat.set_m1_bars(
                                    self.candles.closed_history(tick.symbol, 240)
                                )
                        else:
                            strat.feed(tick)
                    allow_entries = await self._apply_auto_router(tick)
                    if allow_entries and not uses_m3_entry:
                        bars = self.signal_candles.closed_history(tick.symbol, 240)
                        if getattr(self.strategy, "candle_driven", False):
                            if hasattr(self.strategy, "set_m1_bars"):
                                self.strategy.set_m1_bars(
                                    self.candles.closed_history(tick.symbol, 240)
                                )
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

                # Asia M3/M5 strategy: trigger on closed M3 with M5 structure.
                if (
                    signal is None
                    and closed_m3 is not None
                    and uses_m3_entry
                    and getattr(self.strategy, "candle_driven", False)
                ):
                    if hasattr(self.strategy, "set_structure_bars"):
                        self.strategy.set_structure_bars(
                            self.signal_candles.closed_history(tick.symbol, 240)
                        )
                    allow_entries = await self._apply_auto_router(tick)
                    if allow_entries:
                        m3_bars = self.m3_candles.closed_history(tick.symbol, 240)
                        signal = self.strategy.on_bar(m3_bars, tick)

                if signal:
                    self._recent_signals.appendleft(signal)
                    await self._emit("signal", signal.model_dump(mode="json"))
                    signal_db_id = await self._persist_signal(signal)
                    london_id = await self._persist_london(signal)
                    await self._handle_signal(
                        signal,
                        tick,
                        signal_db_id=signal_db_id,
                        london_signal_id=london_id,
                    )

                await self._emit("tick", tick.model_dump(mode="json"))

            for acct in self.accounts.clients():
                await self._emit("account", self.account_payload(acct))
                await self._emit(
                    "positions",
                    {
                        "account_id": acct.id,
                        "positions": [
                            p.model_dump(mode="json") for p in self.open_positions(acct)
                        ],
                    },
                )
            await self._emit("connection", self.connection_info())
            if self.auto_enabled:
                await self._emit("auto", self.auto_status())

    def _auto_fill_targets(self) -> list[PaperAccount]:
        """Accounts that receive auto strategy fills.

        Default: a single paper book only — cloning one SL across every
        follow_auto client was the main loss multiplier (20× same trade).
        """
        if self.using_mt():
            return [self._desk]
        followers = self.accounts.auto_followers()
        if not followers:
            return []
        if not self.settings.auto_fill_single_book:
            return followers
        code = (self.settings.auto_fill_account_code or "").strip().upper()
        if code:
            pinned = [a for a in followers if (a.code or "").upper() == code]
            if pinned:
                return pinned[:1]
        # Stable pick: earliest created account among auto-followers
        followers = sorted(followers, key=lambda a: a.created_at)
        return followers[:1]

    async def _handle_signal(
        self,
        signal: Signal,
        tick: Tick,
        *,
        signal_db_id: str | None = None,
        london_signal_id: str | None = None,
    ) -> None:
        # Desk book never receives client auto fills (unless MT mode).
        targets = self._auto_fill_targets()
        if not targets:
            return
        for acct in targets:
            await self._handle_signal_for_account(
                signal,
                tick,
                account=acct,
                signal_db_id=signal_db_id,
                london_signal_id=london_signal_id,
            )

    async def _handle_signal_for_account(
        self,
        signal: Signal,
        tick: Tick,
        *,
        account: PaperAccount,
        signal_db_id: str | None = None,
        london_signal_id: str | None = None,
    ) -> None:
        # Do NOT reverse open trades on opposite signals — that was the main
        # paper loss driver (EMA flip every M5). Hold until SL/TP / manual close.
        for position in self.open_positions(account):
            if position.symbol == signal.symbol:
                # Same or opposite side: skip — one position at a time, no flip-close
                return

        if (
            signal.order_type == OrderType.LIMIT
            and not self.using_mt()
            and account.broker.pending_orders()
        ):
            return

        entry_px = None
        if tick is not None:
            entry_px = tick.ask if signal.side == Side.BUY else tick.bid
        if signal.limit_price is not None:
            entry_px = signal.limit_price
        advice = None
        if self.advisor.enabled:
            try:
                advice = self.advisor.advise_signal(signal, entry=entry_px)
                self._last_advice = advice.as_dict()
                await self._emit("ai_advice", self._last_advice)
            except Exception:
                advice = None
        if advice is not None and self.advisor.should_block(advice):
            rejected = Order(
                symbol=signal.symbol,
                side=signal.side,
                lots=0.01,
                strategy=signal.strategy,
                comment=(signal.reason or "")[:60],
                status=OrderStatus.REJECTED,
                reject_reason=(
                    f"AI_ML_SKIP p={advice.win_probability:.0%} · "
                    + (advice.reasons[0] if advice.reasons else "low ML win probability")
                ),
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
            await self._journal_fill(
                rejected, signal_db_id=signal_db_id, account=account
            )
            return

        request = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            lots=0.01,
            strategy=signal.strategy,
            comment=signal.reason[:60],
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            order_type=signal.order_type or OrderType.MARKET,
            limit_price=signal.limit_price,
            expire_at=signal.expire_at,
            attach_stops=signal.order_type != OrderType.LIMIT,
        )
        if request.stop_loss is None and signal.stop_loss_pips and tick:
            pip = account.risk.pip_size(signal.symbol)
            entry = tick.ask if signal.side.value == "BUY" else tick.bid
            if signal.side.value == "BUY":
                request.stop_loss = entry - signal.stop_loss_pips * pip
                if signal.take_profit_pips:
                    request.take_profit = entry + signal.take_profit_pips * pip
            else:
                request.stop_loss = entry + signal.stop_loss_pips * pip
                if signal.take_profit_pips:
                    request.take_profit = entry - signal.take_profit_pips * pip
        order = await self._execute(
            request,
            tick=tick,
            signal_db_id=signal_db_id,
            account=account,
        )
        if london_signal_id and order:
            key = f"{account.id}:{order.id}"
            self._london_signal_ids[key] = london_signal_id
            if order.status == OrderStatus.PENDING:
                self._journaled_limit_ids.discard(key)
            elif order.status == OrderStatus.FILLED:
                self._journaled_limit_ids.add(key)
                try:
                    from app.db.repository import mark_london_signal

                    mark_london_signal(
                        london_signal_id,
                        status="EXECUTED",
                        execution_timestamp=order.filled_at,
                    )
                except Exception:
                    pass

    async def _execute(
        self,
        request: OrderRequest,
        tick: Tick | None = None,
        *,
        signal_db_id: str | None = None,
        account: PaperAccount | None = None,
    ) -> Order:
        acct = account or self._desk
        tick = tick or self._recent_ticks.get(request.symbol)
        # Each paper book keeps its own last-tick cache — sync shared feed before fill.
        if tick is not None and not self.using_mt():
            acct.broker._last_ticks[tick.symbol] = tick
        decision = acct.risk.evaluate(
            request,
            balance=self._balance(acct),
            open_positions=self.open_positions(acct),
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
            await self._journal_fill(
                rejected, signal_db_id=signal_db_id, account=acct
            )
            await self._emit(
                "order",
                {**rejected.model_dump(mode="json"), "account_id": acct.id},
            )
            return rejected

        if tick is not None and request.attach_stops:
            sl, tp = acct.risk.apply_default_stops(request, tick)
            request.stop_loss = request.stop_loss or sl
            request.take_profit = request.take_profit or tp

        request.lots = decision.adjusted_lots or request.lots

        if self.using_mt():
            order = self.mt.place_order(request)
            pos = (
                self._latest_open(request.symbol, request.side, acct)
                if order.status == OrderStatus.FILLED
                else None
            )
            await self._journal_fill(order, pos, signal_db_id=signal_db_id, account=acct)
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
                await self._journal_fill(
                    rejected, signal_db_id=signal_db_id, account=acct
                )
                await self._emit(
                    "order",
                    {**rejected.model_dump(mode="json"), "account_id": acct.id},
                )
                return rejected
            order = acct.broker.place_order(request)
            pos = None
            if order.status == OrderStatus.FILLED:
                for p in reversed(acct.broker.positions):
                    if (
                        p.status == PositionStatus.OPEN
                        and p.symbol == request.symbol
                        and p.side == request.side
                    ):
                        pos = p
                        break
            await self._journal_fill(order, pos, signal_db_id=signal_db_id, account=acct)
            self.accounts.save()

        await self._emit(
            "order", {**order.model_dump(mode="json"), "account_id": acct.id}
        )
        await self._emit("account", self.account_payload(acct))
        await self._emit(
            "positions",
            {
                "account_id": acct.id,
                "positions": [
                    p.model_dump(mode="json") for p in self.open_positions(acct)
                ],
            },
        )
        return order
