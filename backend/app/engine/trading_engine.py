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
from app.brokers.mt_bridge import resolve_mt_bridge, resolve_platform_bridge
from app.brokers.paper import PaperBroker
from app.core.config import Settings
from app.engine.candles import CandleAggregator
from app.engine.trade_journal import TradeJournal
from app.engine.mt5_journal_sync import (
    parse_mt5_ticket,
    sync_journal_with_mt5,
    wait_mt_position,
)
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
    TradeStatus,
    utcnow,
)
from app.paper_accounts import PaperAccount, PaperAccountRegistry
from app.risk.manager import RiskDecision, RiskManager
from app.risk.scale_in import (
    evaluate_scale_in,
    leg_add_cooldown_ok,
    mark_leg_added,
    mark_signal_entry,
    open_legs,
    plan_scale_in_entry,
    signal_entry_cooldown_ok,
)
from app.strategies import STRATEGY_REGISTRY, Strategy, create_strategy
from app.strategies.auto_router import AutoStrategyRouter


Listener = Callable[[dict[str, Any]], Awaitable[None] | None]

# Session-follow pool for auto transfer by time.
_AUTO_POOL = (
    "AI_ML",
    "NewsBreakout",
    "EMA_RSI_Scalp",
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
        self.mt4, _ = resolve_platform_bridge(settings, "mt4")
        self.mt4_real, _ = resolve_platform_bridge(settings, "mt4_real")
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
        self._last_mt_journal_sync_at: float = 0.0
        self._last_mt4_journal_sync_at: float = 0.0
        self._last_mt4_real_journal_sync_at: float = 0.0
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
        # Live browser sessions — auto fills prefer connected follow_auto accounts.
        self._connected_accounts: dict[str, float] = {}
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

    def register_connected_account(self, account: PaperAccount) -> None:
        """Track an open desk session for single-book auto-fill routing."""
        if account.is_desk:
            return
        if not account.follow_auto and not self._is_mt_demo_account(account):
            return
        self._connected_accounts[account.id] = time.time()

    def unregister_connected_account(self, account_id: str) -> None:
        self._connected_accounts.pop(account_id, None)

    def _connected_followers(self) -> list[PaperAccount]:
        pool = list(self.accounts.auto_followers())
        for demo_acct in (
            self.mt_demo_account(),
            self.mt4_demo_account(),
            self.mt4_real_account(),
        ):
            if demo_acct is not None and demo_acct.id not in {a.id for a in pool}:
                pool.append(demo_acct)
        if not pool:
            return []
        live = [a for a in pool if a.id in self._connected_accounts]
        live.sort(
            key=lambda a: self._connected_accounts.get(a.id, 0.0),
            reverse=True,
        )
        return live

    def auto_fill_status(self) -> dict[str, Any]:
        followers = self.accounts.auto_followers()
        targets = self._auto_fill_targets()
        selection = "none"
        if targets:
            if not self.settings.auto_fill_single_book:
                selection = "all"
            else:
                target = targets[0]
                pinned = (self.settings.auto_fill_account_code or "").strip().upper()
                if pinned and (target.code or "").upper() == pinned:
                    selection = "pinned"
                elif target.id in self._connected_accounts:
                    selection = "connected"
                else:
                    selection = "earliest"
        target_payload = [
            {
                "account_id": a.id,
                "code": a.code,
                "label": a.label,
            }
            for a in targets
        ]
        return {
            "single_book": self.settings.auto_fill_single_book,
            "pinned_code": (self.settings.auto_fill_account_code or "").strip().upper()
            or None,
            "followers": len(followers),
            "connected_followers": len(self._connected_followers()),
            "selection": selection,
            "targets": target_payload,
            # Back-compat for older UI/clients
            "target": target_payload[0] if target_payload else None,
        }

    def create_client_account(
        self,
        *,
        label: str | None = None,
        deposit: float | None = None,
        follow_auto: bool = True,
        scale_in_mode: bool = False,
    ) -> dict[str, Any]:
        """Provision an isolated paper account for one client browser/session."""
        acct = self.accounts.create(
            deposit=deposit,
            label=label,
            follow_auto=follow_auto,
            is_desk=False,
            scale_in_mode=scale_in_mode,
        )
        return {
            "ok": True,
            "account": acct.snapshot_payload(),
            "token": acct.token,
            "capital": self.capital_preview(acct.broker.deposit, account=acct),
            "trades": self._trades_payload(acct),
            "message": (
                "New scale-in demo account created (up to 3 legs, tier lots)."
                if scale_in_mode
                else (
                    "New demo account created. Only this account id + token can see "
                    "its capital, trades, and history."
                )
            ),
        }

    def create_scale_in_demo_account(
        self,
        *,
        label: str | None = None,
        deposit: float | None = None,
        code: str | None = None,
    ) -> dict[str, Any]:
        """Dedicated paper book for 3-leg scale-in testing — does not alter other accounts."""
        result = self.create_client_account(
            label=label or "Scale-in demo (3 legs)",
            deposit=deposit or 1000.0,
            follow_auto=True,
            scale_in_mode=True,
        )
        if code:
            acct = self.accounts.get(result["account"]["account_id"])
            if acct is not None:
                acct.code = code.strip().upper()
                self.accounts.save()
                result["account"] = acct.snapshot_payload()
        return result

    def _mt_demo_account(self) -> PaperAccount:
        """Journal + auto-fill target when execution_mode is mt4/mt5."""
        code = (self.settings.mt5_demo_account_code or "").strip().upper()
        if code:
            for acct in self.accounts.all():
                if (acct.code or "").upper() == code and not acct.is_desk:
                    return acct
        return self._desk

    def _is_mt5_demo_account(self, account: PaperAccount) -> bool:
        code = (self.settings.mt5_demo_account_code or "").strip().upper()
        return bool(code and (account.code or "").upper() == code)

    def _is_mt4_demo_account(self, account: PaperAccount) -> bool:
        code = (self.settings.mt4_demo_account_code or "").strip().upper()
        return bool(code and (account.code or "").upper() == code)

    def _is_mt4_real_account(self, account: PaperAccount) -> bool:
        code = (self.settings.mt4_real_account_code or "").strip().upper()
        return bool(code and (account.code or "").upper() == code)

    def _is_mt_demo_account(self, account: PaperAccount) -> bool:
        return (
            self._is_mt5_demo_account(account)
            or self._is_mt4_demo_account(account)
            or self._is_mt4_real_account(account)
        )

    def _is_scale_in_account(self, account: PaperAccount) -> bool:
        """Paper scale-in book — isolated from MT-linked and standard demo accounts."""
        return bool(
            getattr(account, "scale_in_mode", False)
            and not account.is_desk
            and not self._is_mt_demo_account(account)
        )

    def _demo_platform(self, account: PaperAccount) -> str | None:
        if self._is_mt5_demo_account(account):
            return "mt5"
        if self._is_mt4_real_account(account):
            return "mt4_real"
        if self._is_mt4_demo_account(account):
            return "mt4"
        return None

    def _bridge_for_account(self, account: PaperAccount | None):
        if account is None:
            return self.mt
        platform = self._demo_platform(account)
        if platform == "mt4":
            return self.mt4
        if platform == "mt4_real":
            return self.mt4_real
        if platform == "mt5":
            return self.mt
        return self.mt if self.using_mt() else None

    def _mt_bridge_live(self, bridge=None) -> bool:
        bridge = bridge if bridge is not None else self.mt
        return bool(bridge and bridge.is_online())

    def _empty_mt_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            balance=0.0,
            equity=0.0,
            margin_used=0.0,
            free_margin=0.0,
            open_positions=0,
            daily_pnl=0.0,
            deposit=0.0,
            paper=False,
        )

    def _mt_account_snapshot(self, account: PaperAccount | None = None) -> AccountSnapshot:
        bridge = self._bridge_for_account(account)
        if bridge and self._mt_bridge_live(bridge):
            return bridge.snapshot()
        return self._empty_mt_snapshot()

    def _linked_mt_accounts(self) -> list[PaperAccount]:
        """All MT-linked JM FX accounts — MT5 demo, MT4 demo, MT4 real (priority order)."""
        out: list[PaperAccount] = []
        seen: set[str] = set()
        for getter in (
            self.mt_demo_account,
            self.mt4_demo_account,
            self.mt4_real_account,
        ):
            acct = getter()
            if acct is not None and acct.id not in seen:
                seen.add(acct.id)
                out.append(acct)
        return out

    def _account_executes_via_mt(self, account: PaperAccount) -> bool:
        return self._is_mt_demo_account(account)

    def mt_demo_account(self) -> PaperAccount | None:
        code = (self.settings.mt5_demo_account_code or "").strip().upper()
        if not code:
            return None
        for acct in self.accounts.all():
            if (acct.code or "").upper() == code and not acct.is_desk:
                return acct
        return None

    def mt4_demo_account(self) -> PaperAccount | None:
        code = (self.settings.mt4_demo_account_code or "").strip().upper()
        if not code:
            return None
        for acct in self.accounts.all():
            if (acct.code or "").upper() == code and not acct.is_desk:
                return acct
        return None

    def mt4_real_account(self) -> PaperAccount | None:
        code = (self.settings.mt4_real_account_code or "").strip().upper()
        if not code:
            return None
        for acct in self.accounts.all():
            if (acct.code or "").upper() == code and not acct.is_desk:
                return acct
        return None

    async def notify_mt4_real_sync(self) -> None:
        """Push live MT4 real balance/positions after EA cloud sync."""
        acct = self.mt4_real_account()
        if acct is None:
            return
        tick = self._recent_ticks.get(self.settings.symbols[0])
        await self._sync_mt_demo_journal(acct, tick=tick, force=True)
        await self._emit("account", self.account_payload(acct))
        await self._emit(
            "positions",
            {
                "account_id": acct.id,
                "positions": [p.model_dump(mode="json") for p in self.open_positions(acct)],
            },
        )
        await self._emit("connection", self.connection_info())

    async def notify_mt_demo_sync(self) -> None:
        """Push live MT5 balance/positions to DDDC3D clients after bridge sync."""
        acct = self.mt_demo_account()
        if acct is None:
            return
        tick = self._recent_ticks.get(self.settings.symbols[0])
        await self._sync_mt_demo_journal(acct, tick=tick, force=True)
        await self._emit("account", self.account_payload(acct))
        await self._emit(
            "positions",
            {
                "account_id": acct.id,
                "positions": [p.model_dump(mode="json") for p in self.open_positions(acct)],
            },
        )
        await self._emit("connection", self.connection_info())

    async def _sync_mt_demo_journal(
        self,
        account: PaperAccount,
        *,
        tick: Tick | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Mirror MT4/MT5 bridge fills/closes into linked JM FX trade log."""
        if not self._is_mt_demo_account(account):
            return {"skipped": True}
        bridge = self._bridge_for_account(account)
        platform = self._demo_platform(account) or "mt5"
        if not bridge or not self._mt_bridge_live(bridge):
            return {"skipped": True}
        throttle_key = {
            "mt4": "_last_mt4_journal_sync_at",
            "mt4_real": "_last_mt4_real_journal_sync_at",
        }.get(platform, "_last_mt_journal_sync_at")
        now = time.time()
        if not force and (now - getattr(self, throttle_key)) < 2.0:
            return {"skipped": True, "reason": "throttled"}
        setattr(self, throttle_key, now)
        symbol = self.settings.symbols[0]
        tick = tick or self._recent_ticks.get(symbol)
        if tick is None and bridge:
            tick = bridge.read_tick()
            if tick:
                self._recent_ticks[tick.symbol] = tick

        before_closed = {
            t.ticket
            for t in account.journal.list(500)
            if t.status == TradeStatus.CLOSED
        }
        result = sync_journal_with_mt5(
            account.journal,
            bridge.open_positions(),
            tick=tick,
            mode=platform,
        )
        account.journal.update_open_pnl(bridge.open_positions())

        for row in account.journal.list(500):
            if row.status != TradeStatus.CLOSED or row.ticket in before_closed:
                continue
            if self.advisor.enabled:
                try:
                    self.advisor.record_close_from_trade(row)
                except Exception:
                    pass
            await self._emit(
                "trade",
                {**row.model_dump(mode="json"), "account_id": account.id},
            )

        if result.get("closed") or result.get("opened") or result.get("updated"):
            await self._emit("trades", self._trades_payload(account))
            await self._emit("ai", self.ai_status())
        return result

    def _configured_code_for_platform(self, platform: str | None) -> str | None:
        if platform == "mt5":
            code = self.settings.mt5_demo_account_code
        elif platform == "mt4_real":
            code = self.settings.mt4_real_account_code
        elif platform == "mt4":
            code = self.settings.mt4_demo_account_code
        else:
            return None
        return (code or "").strip().upper() or None

    def mt_demo_link_status(self, account: PaperAccount) -> dict[str, Any]:
        linked = self._is_mt_demo_account(account)
        platform = self._demo_platform(account)
        bridge = self._bridge_for_account(account) if linked else None
        live = linked and self._mt_bridge_live(bridge)
        tick = bridge.read_tick() if live and bridge else None
        login = None
        symbol = self.settings.mt_symbol
        if platform in {"mt4", "mt4_real"}:
            symbol = self.settings.mt4_symbol
            login = (
                self.settings.mt4_real_login
                if platform == "mt4_real"
                else self.settings.mt4_demo_login
            ) or None
        elif platform == "mt5":
            login = self.settings.mt5_demo_login or None
        return {
            "account_code": account.code if linked else None,
            "configured_code": self._configured_code_for_platform(platform),
            "linked": linked,
            "platform": platform,
            "account_kind": "real" if platform == "mt4_real" else ("demo" if linked else None),
            "mt5_only": platform == "mt5" and linked,
            "mt4_only": platform in {"mt4", "mt4_real"} and linked,
            "mt4_real": platform == "mt4_real" and linked,
            "bridge_online": live,
            "live_balance": live,
            "mt5_login": self.settings.mt5_demo_login or None if platform == "mt5" else None,
            "mt4_login": self.settings.mt4_demo_login or None if platform == "mt4" else None,
            "mt4_real_login": self.settings.mt4_real_login or None if platform == "mt4_real" else None,
            "login": login,
            "symbol": symbol,
            "tick_ok": bool(tick and tick.bid > 0),
        }

    def account_snapshot(self, account: PaperAccount | None = None) -> AccountSnapshot:
        if account is None and self.using_mt():
            return self.mt.snapshot()
        if account and self._is_mt_demo_account(account):
            return self._mt_account_snapshot(account)
        acct = account or self._desk
        return acct.broker.snapshot()

    def account_payload(self, account: PaperAccount | None = None) -> dict[str, Any]:
        acct = account or self._desk
        if account is None and self.using_mt():
            snap = self.mt.snapshot().model_dump(mode="json")
            return {**snap, "account_id": None, "account_code": None}
        if account and self._is_mt_demo_account(account):
            platform = self._demo_platform(account)
            snap = self._mt_account_snapshot(account).model_dump(mode="json")
            return {
                **snap,
                "account_id": acct.id,
                "account_code": acct.code,
                "account_label": acct.label,
                "follow_auto": acct.follow_auto,
                "mt_platform": platform,
                "account_kind": "real" if platform == "mt4_real" else ("demo" if platform else None),
                "mt5_only": platform == "mt5",
                "mt4_only": platform in {"mt4", "mt4_real"},
                "mt4_real": platform == "mt4_real",
                "mt5_linked": platform == "mt5" and self._mt_bridge_live(self.mt),
                "mt4_linked": platform == "mt4" and self._mt_bridge_live(self.mt4),
                "mt4_real_linked": platform == "mt4_real" and self._mt_bridge_live(self.mt4_real),
                "mt5_login": self.settings.mt5_demo_login or None if platform == "mt5" else None,
                "mt4_login": self.settings.mt4_demo_login or None if platform == "mt4" else None,
                "mt4_real_login": self.settings.mt4_real_login or None if platform == "mt4_real" else None,
            }
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
        if account and self._is_mt_demo_account(account):
            bridge = self._bridge_for_account(account)
            return bridge.open_positions() if self._mt_bridge_live(bridge) and bridge else []
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
        self.mt4, _ = resolve_platform_bridge(self.settings, "mt4")
        self.mt4_real, _ = resolve_platform_bridge(self.settings, "mt4_real")
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
        if not self.using_mt():
            mids = dict(self.market.last_mids())
            if mids:
                self.accounts.reconcile_session_restarts(mids)
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
        if not self.using_mt():
            async with self._lock:
                for acct in self.accounts.all():
                    for pos in list(acct.broker.open_positions()):
                        closed = acct.broker.close_position(
                            pos.id, reason="session_restart"
                        )
                        if closed:
                            acct.risk.record_realized_pnl(closed.realized_pnl)
                            acct.journal.record_close(closed)
                    acct.journal.update_open_pnl(acct.broker.open_positions())
                self.accounts.save()
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
        # AI_ML is the session stack — keep auto session-follow ON so stand-aside
        # parks the next slot instead of locking the desk on manual_only forever.
        self.auto_enabled = name == "AI_ML"
        self._strategies[name] = create_strategy(name)
        self._bind_advisor(self._strategies[name])
        self.active_name = name
        self.strategy = self._strategies[name]
        self._last_strategy_switch_at = time.time()
        self._last_auto_key = None
        if name == "AI_ML":
            self._last_transfer_note = "AI_ML armed · session-follow ON"

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
            "auto_fill": self.auto_fill_status(),
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
            slot = nxt.get("session") or "next session"
            if hour is not None:
                note = f"Stand aside now — armed {target} for {slot} @ {hour}:00 UTC"
            else:
                note = f"Stand aside now — armed {target} for {slot}"
            return target, note
        # Never park on manual_only when AI_ML exists — weekend/off-hours must
        # wake into the session stack, not a dead manual desk.
        if "AI_ML" in STRATEGY_REGISTRY:
            return "AI_ML", "Stand aside — AI_ML armed for next tradeable session"
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
            if not self._is_scale_in_account(acct):
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
        """Show how risk / lot sizing scales with account capital."""
        acct = account or self._desk
        if account and self._is_mt_demo_account(account):
            snap = self._mt_account_snapshot(account)
            amount = float(deposit if deposit is not None else snap.equity or snap.balance)
            platform = self._demo_platform(account) or "mt5"
            bridge = self._bridge_for_account(account)
            symbol = self.settings.mt_symbol if platform == "mt5" else self.settings.mt4_symbol
            kind = "real" if platform == "mt4_real" else "demo"
            if self._mt_bridge_live(bridge):
                note = f"MT4 {kind} — balance from XM terminal"
            else:
                note = f"MT4 {kind} offline — attach JM_Forex_Bridge on {symbol} chart"
            if platform == "mt5":
                if self._mt_bridge_live(bridge):
                    note = "MT5 live account — balance from XM demo terminal"
                else:
                    note = f"MT5 offline — attach JM_Forex_Bridge on {symbol} chart"
            paper = False
        else:
            amount = float(deposit if deposit is not None else acct.broker.deposit)
            if self._is_scale_in_account(acct):
                from app.risk.scale_in import scale_in_lots

                if self.settings.scale_in_structure_pullback:
                    note = (
                        "Scale-in demo — up to 3 legs on M1 structure pullbacks "
                        f"({self.settings.scale_in_min_pullback_atr:g}×ATR + swing zone). "
                        "Other accounts unchanged."
                    )
                else:
                    note = (
                        "Scale-in demo — up to 3 legs on pullbacks "
                        f"({self.settings.scale_in_step_pips:g}p steps). "
                        "Other accounts unchanged."
                    )
            else:
                note = "Paper demo capital for this account only — other clients cannot see it"
            paper = not self.using_mt()
        risk_pct = float(self.settings.max_risk_per_trade_pct)
        daily_pct = float(self.settings.max_daily_loss_pct)
        stop_pips = float(self.settings.default_stop_loss_pips)
        tp_pips = float(self.settings.default_take_profit_pips)
        risk_usd = amount * (risk_pct / 100.0)
        daily_usd = amount * (daily_pct / 100.0) if daily_pct > 0 else None
        pip_value_per_lot = 10.0  # XAUUSD desk convention in RiskManager
        suggested = risk_usd / (stop_pips * pip_value_per_lot) if stop_pips > 0 else 0.01
        suggested_lots = max(0.01, round(suggested, 2))
        scale_in_lots_preview = None
        if account and self._is_scale_in_account(acct):
            from app.risk.scale_in import scale_in_lots as si_lots

            scale_in_lots_preview = [
                si_lots(amount, leg, self.settings)
                for leg in range(1, int(self.settings.scale_in_max_legs) + 1)
            ]
        return {
            "deposit": round(amount, 2),
            "currency": self.settings.base_currency,
            "paper": paper,
            "scale_in_mode": bool(account and self._is_scale_in_account(acct)),
            "scale_in_max_legs": int(self.settings.scale_in_max_legs)
            if account and self._is_scale_in_account(acct)
            else None,
            "scale_in_lots": scale_in_lots_preview,
            "scale_in_structure_pullback": bool(
                self.settings.scale_in_structure_pullback
            )
            if account and self._is_scale_in_account(acct)
            else None,
            "scale_in_min_pullback_atr": float(self.settings.scale_in_min_pullback_atr)
            if account
            and self._is_scale_in_account(acct)
            and self.settings.scale_in_structure_pullback
            else None,
            "scale_in_step_pips": float(self.settings.scale_in_step_pips)
            if account
            and self._is_scale_in_account(acct)
            and not self.settings.scale_in_structure_pullback
            else None,
            "mt5_only": bool(account and self._is_mt5_demo_account(account)),
            "mt4_only": bool(account and self._is_mt4_demo_account(account)),
            "mt4_real": bool(account and self._is_mt4_real_account(account)),
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
            "note": note,
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
        if self._is_mt_demo_account(acct):
            platform = self._demo_platform(acct) or "MT"
            label = platform.upper().replace("_", " ")
            raise ValueError(
                f"Account {acct.code} is {label}-only — balance comes from XM terminal, not paper deposit"
            )
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

    def _position_uses_asia_stops(self, pos: Position) -> bool:
        if pos.leg_index is not None and pos.leg_index > 1:
            return False
        return (pos.strategy or "") in {"EMA_RSI_Scalp", "AI_ML"}

    def _asia_levels_for_position(self, pos: Position):
        from app.strategies.asia_stops import refresh_asia_position_stops
        from app.strategies.entry_setup import true_atr

        bars = self.signal_candles.closed_history(pos.symbol, 240)
        atr = true_atr(bars, 14)
        if not bars or atr is None:
            return None
        return refresh_asia_position_stops(
            pos.side,
            entry=pos.entry_price,
            candles=bars,
            atr=atr,
            sl_tp_scale=pos.sl_tp_scale or 1.0,
        )

    async def _maybe_dynamic_asia_stops(self, tick: Tick) -> None:
        if not self.settings.asia_dynamic_stops:
            return
        from app.strategies.asia_stops import refresh_asia_position_stops, stops_materially_changed
        from app.strategies.entry_setup import true_atr
        from app.strategies.session import classify_session

        session = classify_session(tick.timestamp)
        if session.label not in {"asia", "off_hours"}:
            return

        bars = self.signal_candles.closed_history(tick.symbol, 240)
        atr = true_atr(bars, 14)
        if not bars or atr is None or atr <= 0:
            return

        for acct in self.accounts.all():
            if self._is_mt_demo_account(acct) or self._account_executes_via_mt(acct):
                continue
            changed = False
            for pos in acct.broker.open_positions():
                if not self._position_uses_asia_stops(pos) or not pos.vol_auto_stops:
                    continue
                levels = refresh_asia_position_stops(
                    pos.side,
                    entry=pos.entry_price,
                    candles=bars,
                    atr=atr,
                    sl_tp_scale=pos.sl_tp_scale or 1.0,
                )
                if levels is None:
                    continue
                if not stops_materially_changed(
                    stop_loss=pos.stop_loss,
                    take_profit=pos.take_profit,
                    new_sl=levels.stop_loss,
                    new_tp=levels.take_profit,
                ):
                    continue
                updated = acct.broker.set_stops(
                    pos.id,
                    stop_loss=levels.stop_loss,
                    take_profit=levels.take_profit,
                )
                if updated:
                    changed = True
            if changed:
                acct.journal.update_open_pnl(acct.broker.open_positions())
                await self._emit(
                    "positions",
                    {
                        "account_id": acct.id,
                        "positions": [
                            p.model_dump(mode="json") for p in self.open_positions(acct)
                        ],
                    },
                )

    async def set_position_stops(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        auto: bool = False,
        stop_loss_pips: float | None = None,
        take_profit_pips: float | None = None,
        scale: float | None = None,
        vol_auto: bool | None = None,
        account: PaperAccount | None = None,
    ) -> Position | None:
        """Attach / update SL & TP on an open position (manual desk helper)."""
        acct = account or self._desk
        async with self._lock:
            if self.using_mt() or self._account_executes_via_mt(acct):
                return None  # MT modify not supported via file bridge yet
            pos = next(
                (p for p in acct.broker.open_positions() if p.id == position_id),
                None,
            )
            if pos is None:
                return None
            if vol_auto is not None:
                pos.vol_auto_stops = vol_auto
            if scale is not None:
                pos.sl_tp_scale = max(0.5, min(2.0, (pos.sl_tp_scale or 1.0) * scale))

            sl = stop_loss
            tp = take_profit
            pip = 0.1
            if stop_loss_pips is not None or take_profit_pips is not None:
                pos.vol_auto_stops = False
                entry = pos.entry_price
                if stop_loss_pips is not None:
                    dist = float(stop_loss_pips) * pip
                    sl = entry - dist if pos.side == Side.BUY else entry + dist
                if take_profit_pips is not None:
                    dist = float(take_profit_pips) * pip
                    tp = entry + dist if pos.side == Side.BUY else entry - dist
            elif scale is not None and sl is None and tp is None:
                levels = self._asia_levels_for_position(pos)
                if levels is not None:
                    sl, tp = levels.stop_loss, levels.take_profit
            elif auto or (sl is None and tp is None):
                levels = self._asia_levels_for_position(pos)
                if levels is not None:
                    sl, tp = levels.stop_loss, levels.take_profit
                else:
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
        ticks = self.market.next_ticks()
        # Keep MT5 live price available for DDDC3D / manual orders even in paper desk mode.
        if self.mt and self._mt_bridge_live():
            mt_tick = self.mt.read_tick()
            if mt_tick:
                self._recent_ticks[mt_tick.symbol] = mt_tick
                for i, t in enumerate(ticks):
                    if t.symbol == mt_tick.symbol:
                        ticks[i] = mt_tick
                        break
                else:
                    ticks.append(mt_tick)
        return ticks

    async def _tick_once(self) -> None:
        async with self._lock:
            ticks = await self._next_ticks()
            for tick in ticks:
                self.ticks_processed += 1
                self.last_tick_at = tick.timestamp
                self._recent_ticks[tick.symbol] = tick

                if not self.using_mt():
                    for acct in self.accounts.all():
                        if self._is_mt_demo_account(acct):
                            continue
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
                    mt_acct = self.mt_demo_account()
                    if mt_acct is not None and self._mt_bridge_live(self.mt):
                        await self._sync_mt_demo_journal(mt_acct, tick=tick)
                    mt4_acct = self.mt4_demo_account()
                    if mt4_acct is not None and self._mt_bridge_live(self.mt4):
                        await self._sync_mt_demo_journal(mt4_acct, tick=tick)
                    mt4_real_acct = self.mt4_real_account()
                    if mt4_real_acct is not None and self._mt_bridge_live(self.mt4_real):
                        await self._sync_mt_demo_journal(mt4_real_acct, tick=tick)
                    await self._london_kill_switch(tick)

                closed_candle, forming = self.candles.update(tick)
                if closed_candle is not None:
                    await self._emit("candle_closed", closed_candle.model_dump(mode="json"))
                    await self._maybe_scale_in_adds(tick)
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
                    await self._maybe_dynamic_asia_stops(tick)
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
                    await self._handle_signal(
                        signal,
                        tick,
                        signal_db_id=signal_db_id,
                        london_signal_id=None,
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

        One desk strategy signal fans out to every auto-follow client — same
        AI_ML / EMA_RSI / SMC setup for all books. MT-linked accounts execute
        on their bridge first; paper accounts fill on their own book.
        """
        linked_mt = self._linked_mt_accounts()
        followers = self.accounts.auto_followers()

        def _prepend_linked_mt(pool: list[PaperAccount]) -> list[PaperAccount]:
            if not linked_mt:
                return pool
            pool_ids = {a.id for a in pool}
            mt_in_pool = [a for a in linked_mt if a.id in pool_ids]
            mt_extra = [
                a for a in linked_mt if a.id not in pool_ids and a.follow_auto
            ]
            ordered_mt = mt_in_pool + mt_extra
            seen = {a.id for a in ordered_mt}
            rest = [a for a in pool if a.id not in seen]
            return [*ordered_mt, *rest]

        if not self.settings.auto_fill_single_book:
            return _prepend_linked_mt(followers)

        code = (self.settings.auto_fill_account_code or "").strip().upper()
        if code:
            pinned = [
                a
                for a in self.accounts.clients()
                if (a.code or "").upper() == code
            ]
            if pinned:
                return pinned[:1]
        connected = self._connected_followers()
        if connected:
            return connected[:1]
        if followers:
            followers = sorted(followers, key=lambda a: a.created_at)
            return followers[:1]
        if linked_mt:
            return linked_mt[:1]
        return []

    async def _handle_scale_in_signal_for_account(
        self,
        signal: Signal,
        tick: Tick,
        *,
        account: PaperAccount,
        signal_db_id: str | None = None,
        london_signal_id: str | None = None,
        defer_save: bool = False,
    ) -> None:
        """Up to 3 same-side legs on pullbacks — scale-in paper account only."""
        opens = self.open_positions(account)
        for position in opens:
            if position.symbol == signal.symbol and position.side != signal.side:
                return

        legs = open_legs(opens, symbol=signal.symbol, side=signal.side)
        plan = plan_scale_in_entry(
            symbol=signal.symbol,
            side=signal.side,
            balance=self._balance(account),
            open_positions=opens,
            tick=tick,
            settings=self.settings,
            require_depth=len(legs) > 0,
        )
        if not plan.allowed:
            return

        if plan.leg == 1 and not signal_entry_cooldown_ok(
            account.id, float(self.settings.entry_cooldown_seconds)
        ):
            return

        if plan.leg > 1 and not leg_add_cooldown_ok(
            account.id, float(self.settings.scale_in_leg_cooldown_seconds)
        ):
            return

        entry_px = tick.ask if signal.side == Side.BUY else tick.bid if tick else None
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
        if (
            advice is not None
            and (signal.strategy or "") != "NewsBreakout"
            and self.advisor.should_block(advice)
        ):
            rejected = Order(
                symbol=signal.symbol,
                side=signal.side,
                lots=plan.lots,
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
            lots=plan.lots,
            strategy=signal.strategy,
            comment=f"{(signal.reason or '')[:48]}|L{plan.leg}",
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            order_type=signal.order_type or OrderType.MARKET,
            limit_price=signal.limit_price,
            expire_at=signal.expire_at,
            attach_stops=signal.order_type != OrderType.LIMIT,
            setup_id=plan.setup_id,
            leg_index=plan.leg,
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
            defer_save=defer_save,
        )
        if order.status == OrderStatus.FILLED:
            mark_leg_added(account.id)
            if plan.leg == 1:
                mark_signal_entry(account.id)

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

    async def _maybe_scale_in_adds(self, tick: Tick) -> None:
        """M1 pullback adds for scale-in demo accounts (legs 2–3, no new M5 signal)."""
        for acct in self.accounts.auto_followers():
            if not self._is_scale_in_account(acct):
                continue
            if not leg_add_cooldown_ok(
                acct.id, float(self.settings.scale_in_leg_cooldown_seconds)
            ):
                continue
            opens = self.open_positions(acct)
            if not opens:
                continue
            seen: set[tuple[str, str]] = set()
            for pos in opens:
                key = (pos.symbol, pos.side.value)
                if key in seen:
                    continue
                seen.add(key)
                legs = open_legs(opens, symbol=pos.symbol, side=pos.side)
                if len(legs) >= int(self.settings.scale_in_max_legs):
                    continue
                m1_bars = self.candles.closed_history(pos.symbol, 240)
                from app.strategies.entry_setup import true_atr

                atr = true_atr(m1_bars, 14) if m1_bars else None
                plan = plan_scale_in_entry(
                    symbol=pos.symbol,
                    side=pos.side,
                    balance=self._balance(acct),
                    open_positions=opens,
                    tick=tick,
                    settings=self.settings,
                    require_depth=True,
                    candles=m1_bars,
                    atr=atr,
                )
                if not plan.allowed or plan.leg <= 1:
                    continue
                anchor = legs[0]
                request = OrderRequest(
                    symbol=pos.symbol,
                    side=pos.side,
                    lots=plan.lots,
                    strategy=anchor.strategy or "scale_in",
                    comment=f"scale_in_structure|L{plan.leg}",
                    stop_loss=anchor.stop_loss,
                    take_profit=anchor.take_profit,
                    attach_stops=anchor.stop_loss is None and anchor.take_profit is None,
                    setup_id=plan.setup_id,
                    leg_index=plan.leg,
                )
                order = await self._execute(request, tick=tick, account=acct)
                if order.status == OrderStatus.FILLED:
                    mark_leg_added(acct.id)

    async def _handle_signal(
        self,
        signal: Signal,
        tick: Tick,
        *,
        signal_db_id: str | None = None,
        london_signal_id: str | None = None,
    ) -> None:
        targets = self._auto_fill_targets()
        if not targets:
            return

        entry_px = None
        if tick is not None:
            entry_px = tick.ask if signal.side == Side.BUY else tick.bid
        if signal.limit_price is not None:
            entry_px = signal.limit_price

        cached_advice = None
        if self.advisor.enabled:
            try:
                cached_advice = self.advisor.advise_signal(signal, entry=entry_px)
                self._last_advice = cached_advice.as_dict()
                await self._emit("ai_advice", self._last_advice)
            except Exception:
                cached_advice = None

        if cached_advice is not None and self.advisor.should_block(cached_advice):
            await asyncio.gather(
                *[
                    self._journal_fill(
                        Order(
                            symbol=signal.symbol,
                            side=signal.side,
                            lots=0.01,
                            strategy=signal.strategy,
                            comment=(signal.reason or "")[:60],
                            status=OrderStatus.REJECTED,
                            reject_reason=(
                                f"AI_ML_SKIP p={cached_advice.win_probability:.0%} · "
                                + (
                                    cached_advice.reasons[0]
                                    if cached_advice.reasons
                                    else "low ML win probability"
                                )
                            ),
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                        ),
                        signal_db_id=signal_db_id,
                        account=acct,
                    )
                    for acct in targets
                ]
            )
            return

        mt_targets = [a for a in targets if self._account_executes_via_mt(a)]
        paper_targets = [a for a in targets if not self._account_executes_via_mt(a)]

        async def _mt_for_bridge(accts: list[PaperAccount]) -> None:
            for acct in accts:
                await self._handle_signal_for_account(
                    signal,
                    tick,
                    account=acct,
                    signal_db_id=signal_db_id,
                    london_signal_id=london_signal_id,
                    cached_advice=cached_advice,
                )

        async def _paper_fan_out() -> None:
            if not paper_targets:
                return
            await asyncio.gather(
                *[
                    self._handle_signal_for_account(
                        signal,
                        tick,
                        account=acct,
                        signal_db_id=signal_db_id,
                        london_signal_id=london_signal_id,
                        cached_advice=cached_advice,
                        defer_save=True,
                    )
                    for acct in paper_targets
                ]
            )
            self.accounts.save()

        by_bridge: dict[str, list[PaperAccount]] = {}
        for acct in mt_targets:
            key = self._demo_platform(acct) or "mt5"
            by_bridge.setdefault(key, []).append(acct)
        fan_out: list[Any] = [_paper_fan_out()]
        if by_bridge:
            fan_out.extend(_mt_for_bridge(accts) for accts in by_bridge.values())
        await asyncio.gather(*fan_out)

    async def _handle_signal_for_account(
        self,
        signal: Signal,
        tick: Tick,
        *,
        account: PaperAccount,
        signal_db_id: str | None = None,
        london_signal_id: str | None = None,
        cached_advice: Any | None = None,
        defer_save: bool = False,
    ) -> None:
        if self._is_scale_in_account(account):
            await self._handle_scale_in_signal_for_account(
                signal,
                tick,
                account=account,
                signal_db_id=signal_db_id,
                london_signal_id=london_signal_id,
                defer_save=defer_save,
            )
            return

        # Do NOT reverse open trades on opposite signals — that was the main
        # paper loss driver (EMA flip every M5). Hold until SL/TP / manual close.
        for position in self.open_positions(account):
            if position.symbol == signal.symbol:
                # Same or opposite side: skip — one position at a time, no flip-close
                return

        if (
            signal.order_type == OrderType.LIMIT
            and not self.using_mt()
            and not self._account_executes_via_mt(account)
            and account.broker.pending_orders()
        ):
            return

        entry_px = None
        if tick is not None:
            entry_px = tick.ask if signal.side == Side.BUY else tick.bid
        if signal.limit_price is not None:
            entry_px = signal.limit_price
        advice = cached_advice
        if advice is None and self.advisor.enabled:
            try:
                advice = self.advisor.advise_signal(signal, entry=entry_px)
                self._last_advice = advice.as_dict()
                await self._emit("ai_advice", self._last_advice)
            except Exception:
                advice = None
        if (
            advice is not None
            and (signal.strategy or "") != "NewsBreakout"
            and self.advisor.should_block(advice)
        ):
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
            defer_save=defer_save,
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
        defer_save: bool = False,
    ) -> Order:
        acct = account or self._desk
        tick = tick or self._recent_ticks.get(request.symbol)
        via_mt = self.using_mt() or self._account_executes_via_mt(acct)
        # Each paper book keeps its own last-tick cache — sync shared feed before fill.
        if tick is not None and not via_mt:
            acct.broker._last_ticks[tick.symbol] = tick
        if not via_mt and acct.risk.daily_loss_hit():
            # Capital-protection circuit breaker — applies to every paper book,
            # including scale-in accounts (which size their own lots below and
            # would otherwise bypass this check entirely).
            decision = RiskDecision(
                False,
                f"Daily loss limit hit ({self.settings.max_daily_loss_pct}%)",
            )
        elif self._is_scale_in_account(acct) and not via_mt:
            decision = evaluate_scale_in(
                request,
                balance=self._balance(acct),
                open_positions=self.open_positions(acct),
                tick=tick,
                settings=self.settings,
            )
        else:
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

        if via_mt:
            bridge = self._bridge_for_account(acct)
            platform = self._demo_platform(acct) or self._mt_platform
            symbol = self.settings.mt_symbol if platform == "mt5" else self.settings.mt4_symbol
            label = platform.upper().replace("_", " ")
            if not self._mt_bridge_live(bridge):
                rejected = Order(
                    symbol=request.symbol,
                    side=request.side,
                    lots=request.lots,
                    strategy=request.strategy,
                    comment=request.comment,
                    status=OrderStatus.REJECTED,
                    reject_reason=f"{label} bridge offline — attach JM_Forex_Bridge on {symbol}",
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
            order = await asyncio.to_thread(bridge.place_order, request)
            row = None
            if order.status == OrderStatus.FILLED:
                mt_pos = None
                ticket = parse_mt5_ticket(order)
                if ticket:
                    mt_pos = wait_mt_position(bridge, ticket)
                if mt_pos is None:
                    mt_pos = self._latest_open(request.symbol, request.side, acct)
                if mt_pos is not None:
                    mt_pos = mt_pos.model_copy(update={"strategy": request.strategy})
                    order.fill_price = mt_pos.entry_price
                    row = acct.journal.record_mt5_open(order, mt_pos, mode=platform)
                    self._arm_entry_cooldown()
                    await self._persist_trade_open(
                        order, mt_pos, signal_db_id=signal_db_id
                    )
                    if self.advisor.enabled:
                        try:
                            self.advisor.record_open_from_trade(
                                row, account_id=acct.id, mode=platform
                            )
                        except Exception:
                            pass
                else:
                    row = acct.journal.record_order(order, mode=platform)
            else:
                row = acct.journal.record_order(order, mode=platform)
            if row is not None:
                await self._emit(
                    "trade", {**row.model_dump(mode="json"), "account_id": acct.id}
                )
                await self._emit("trades", self._trades_payload(acct))
            await self._sync_mt_demo_journal(acct, tick=tick, force=True)
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
            if not defer_save:
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
