from __future__ import annotations

import asyncio
import math
import random
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from app.brokers.market_data import MarketDataSimulator
from app.brokers.mt_bridge import resolve_dual_remote_bridges, resolve_mt_bridge
from app.brokers.paper import PaperBroker
from app.brokers.remote_mt_store import get_remote_mt_state
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
    TradeStatus,
    utcnow,
)
from app.paper_accounts import PaperAccount, PaperAccountRegistry
from app.risk.manager import RiskManager
from app.strategies import STRATEGY_REGISTRY, Strategy, create_strategy
from app.strategies.auto_router import AutoStrategyRouter


Listener = Callable[[dict[str, Any]], Awaitable[None] | None]

# Session-follow pool for auto transfer by time.
_AUTO_POOL = (
    "EMA_RSI_Scalp",
    "London_Judas_Sweep",
    "Liquidity_Sweep_SMC",
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
        # Always keep BTCUSD paper tape ready for manual BTC strategy.
        self.market.ensure_symbol("BTCUSD")
        if settings.paper_sync_live_gold:
            self.market.set_live_mid_provider(self._live_market_mid)
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
        self.bridges = resolve_dual_remote_bridges(settings)
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
        if self.bridges and self.mode in self.bridges:
            self.mt = self.bridges[self.mode]
            self._mt_platform = self.mode
        self._last_auto_key: str | None = None
        self._last_strategy_switch_at: float = 0.0
        self._entry_cooldown_until: float = 0.0
        self._last_session_slot: str | None = None
        self._last_transfer_note: str | None = None
        self._journaled_limit_ids: set[str] = set()
        self._london_signal_ids: dict[str, str] = {}  # order.id -> london_signal uuid
        self._last_hourly_transfer_at: float = 0.0
        self._last_transfer_hour_key: str | None = None

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
        password: str | None = None,
        avatar: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        mt5_login: str | None = None,
        mt_platform: str | None = None,
    ) -> dict[str, Any]:
        """Provision an isolated account for one client browser/session.

        MT-linked clients (mt5_login set) do not use paper deposit — live MT
        equity is shown when the Windows bridge is online and bound.
        """
        mt5 = str(mt5_login or "").strip()
        if mt5:
            # Internal stub only — never shown as capital for MT clients.
            deposit = 50.0
        acct = self.accounts.create(
            deposit=deposit,
            label=label,
            follow_auto=follow_auto,
            is_desk=False,
            password=password,
            avatar=avatar,
            first_name=first_name,
            last_name=last_name,
            email=email,
            mt5_login=mt5_login,
            mt_platform=mt_platform,
        )
        plat = acct.mt_platform or ("mt5" if mt5 else "")
        return {
            "ok": True,
            "account": self.account_payload(acct),
            "token": acct.token,
            "capital": self.capital_preview(account=acct),
            "trades": self._trades_payload(acct),
            "message": (
                f"{plat.upper()} account linked. Login with your MT number + password. "
                "Balance comes from live MT when the matching bridge agent is online — no paper deposit."
                if mt5
                else (
                    "New demo account created. Save your account code + password — "
                    "only this login can see its capital, trades, and history."
                )
            ),
        }

    def login_client_account(self, *, code: str, password: str) -> dict[str, Any]:
        """Authenticate by MT5 account + password. Trade history is never reset."""
        acct = self.accounts.authenticate(code, password)
        return {
            "ok": True,
            "account": self.account_payload(acct),
            "token": acct.token,
            "capital": self.capital_preview(account=acct),
            "trades": self._trades_payload(acct),
            "message": f"Signed in as {acct.mt5_login or acct.code} — trade history kept.",
        }

    def update_client_profile(
        self,
        account: PaperAccount,
        *,
        label: str | None = None,
        avatar: str | None = ...,  # type: ignore[assignment]
        mt_platform: str | None = ...,  # type: ignore[assignment]
    ) -> dict[str, Any]:
        self.accounts.update_profile(
            account, label=label, avatar=avatar, mt_platform=mt_platform
        )
        plat = account.mt_platform or None
        msg = "Profile updated — trade history unchanged."
        if plat in {"mt4", "mt5"}:
            msg = (
                f"Profile updated — this account is live {plat.upper()}. "
                f"Use RUN_AGENT_{plat.upper()}.bat + matching EA."
            )
        return {
            "ok": True,
            "account": self.account_payload(account),
            "message": msg,
        }

    def change_client_password(
        self,
        account: PaperAccount,
        *,
        new_password: str,
        current_password: str | None = None,
    ) -> dict[str, Any]:
        self.accounts.set_password(
            account,
            new_password=new_password,
            current_password=current_password,
        )
        return {
            "ok": True,
            "account": self.account_payload(account),
            "has_password": True,
            "message": "Password updated — trade history unchanged.",
        }

    def set_client_trade_settings(
        self,
        account: PaperAccount,
        *,
        fixed_lots: float | None = ...,  # type: ignore[assignment]
        preferred_strategy: str | None = ...,  # type: ignore[assignment]
    ) -> dict[str, Any]:
        """Manual lots + saved preferred strategy (manual select/save)."""
        if fixed_lots is not ...:
            self.accounts.set_fixed_lots(account, fixed_lots)
        if preferred_strategy is not ...:
            self.accounts.set_preferred_strategy(account, preferred_strategy)
        saved = account.preferred_strategy
        return {
            "ok": True,
            "account": self.account_payload(account),
            "fixed_lots": account.fixed_lots,
            "preferred_strategy": saved,
            "capital": self.capital_preview(account=account),
            "message": (
                (
                    f"Saved strategy {saved} + lots "
                    f"{account.fixed_lots:.2f}."
                    if account.fixed_lots is not None and saved
                    else f"Saved preferred strategy: {saved}."
                    if saved
                    else (
                        f"Manual lots set to {account.fixed_lots:.2f}."
                        if account.fixed_lots is not None
                        else "Trade settings updated."
                    )
                )
            ),
        }

    def account_snapshot(self, account: PaperAccount | None = None) -> AccountSnapshot:
        if self.is_mt_bound(account):
            bridge = self.bridge_for_account(account)
            if bridge is not None:
                return bridge.snapshot()
        if account is not None and self.is_mt5_client(account):
            return AccountSnapshot(
                balance=0.0,
                equity=0.0,
                margin_used=0.0,
                free_margin=0.0,
                open_positions=0,
                daily_pnl=0.0,
                currency=self.settings.base_currency,
                deposit=0.0,
                paper=False,
            )
        acct = account or self._desk
        return acct.broker.snapshot()

    def account_payload(self, account: PaperAccount | None = None) -> dict[str, Any]:
        acct = account or self._desk
        if account is None and self.using_mt():
            # Desk overview: prefer MT5, else MT4
            bridge = None
            if self.bridges:
                bridge = (
                    self.bridges["mt5"]
                    if self.bridges["mt5"].is_online()
                    else self.bridges.get("mt4")
                )
            bridge = bridge or self.mt
            snap = bridge.snapshot().model_dump(mode="json") if bridge else {}
            plat = getattr(bridge, "platform", self._mt_platform)
            return {
                **snap,
                "account_id": None,
                "account_code": self.connected_mt_login(plat if plat in {"mt4", "mt5"} else None),
                "mt5_login": self.connected_mt_login(plat if plat in {"mt4", "mt5"} else None),
                "mt_bound": True,
                "mt_platform": plat,
                "binding": f"live_{plat}" if plat in {"mt4", "mt5"} else "live_mt",
            }
        if account is not None and self.is_mt5_client(account):
            plat = self.account_mt_platform(account) or "mt5"
            # MT-linked clients never show fake paper deposit as capital.
            if self.is_mt_bound(account):
                bridge = self.bridge_for_account(account)
                snap = bridge.snapshot().model_dump(mode="json") if bridge else {}
                return {
                    **snap,
                    **acct.profile_public(),
                    "paper": False,
                    "mt_bound": True,
                    "mt_online": True,
                    "mt_platform": plat,
                    "mt5_login": acct.mt5_login or acct.code,
                    "binding": f"live_{plat}",
                }
            connected = self.connected_mt_login(plat)
            return {
                **acct.profile_public(),
                "balance": 0.0,
                "equity": 0.0,
                "margin_used": 0.0,
                "free_margin": 0.0,
                "open_positions": 0,
                "daily_pnl": 0.0,
                "currency": self.settings.base_currency,
                "deposit": 0.0,
                "paper": False,
                "mt_bound": False,
                "mt_online": bool(
                    self.bridges.get(plat).is_online()
                    if self.bridges and plat in self.bridges
                    else self.mt_online()
                ),
                "mt_platform": plat,
                "mt5_login": acct.mt5_login or acct.code,
                "connected_mt_login": connected,
                "binding": "waiting_mt",
                "note": (
                    f"{plat.upper()} bridge offline — open {plat.upper()} + JM_Forex_Bridge EA + RUN_AGENT_{plat.upper()}.bat"
                    if not (
                        self.bridges.get(plat).is_online()
                        if self.bridges and plat in self.bridges
                        else False
                    )
                    else (
                        f"Connected {plat.upper()} login does not match this account "
                        f"(connected={connected}, yours={acct.mt5_login or acct.code})"
                    )
                ),
            }
        payload = acct.snapshot_payload()
        payload["mt_bound"] = False
        payload["binding"] = "paper"
        payload["mt_platform"] = None
        return payload

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
        if account is not None and self.is_mt_bound(account):
            bridge = self.bridge_for_account(account)
            if bridge is not None:
                return bridge.open_positions()
        if account is None and self.using_mt():
            bridge = self.mt
            if self.bridges:
                bridge = (
                    self.bridges["mt5"]
                    if self.bridges["mt5"].is_online()
                    else self.bridges.get("mt4") or self.mt
                )
            return bridge.open_positions() if bridge else []
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
        self.bridges = resolve_dual_remote_bridges(self.settings)
        if self.bridges and mode in self.bridges:
            self.mt = self.bridges[mode]
            self._mt_platform = mode
        # Keep live-gold mid for paper books even when MT bridge mode is enabled.
        # Global mt4/mt5 only means the Windows agent is available for bound accounts.
        if self.settings.paper_sync_live_gold:
            self.market.set_live_mid_provider(self._live_gold_mid)
        else:
            self.market.set_live_mid_provider(None)

    def mt_online(self) -> bool:
        if self.bridges:
            return any(b.is_online() for b in self.bridges.values())
        return bool(self.mt and self.mt.is_online())

    def using_mt(self) -> bool:
        # Dual remote: either platform online counts as live feed available.
        if self.bridges:
            return self.mt_online()
        return self.mode in {"mt4", "mt5"} and self.mt_online()

    def account_mt_platform(self, account: PaperAccount | None) -> str | None:
        """Which live terminal this account is linked to (mt4/mt5)."""
        if account is None or not self.is_mt5_client(account):
            return None
        raw = str(getattr(account, "mt_platform", None) or "").strip().lower()
        if raw in {"mt4", "mt5"}:
            return raw
        # Infer from whichever bridge currently reports this login.
        want = str(account.mt5_login or "").strip()
        try:
            from app.brokers.remote_mt_store import remote_mt_login

            if want and remote_mt_login("mt4") == want:
                return "mt4"
            if want and remote_mt_login("mt5") == want:
                return "mt5"
        except Exception:
            pass
        return "mt5"

    def bridge_for_account(self, account: PaperAccount | None):
        """Remote bridge for a live-linked account, or None."""
        plat = self.account_mt_platform(account)
        if not plat:
            return None
        if self.bridges and plat in self.bridges:
            return self.bridges[plat]
        if self.mt and self._mt_platform == plat:
            return self.mt
        return None

    def connected_mt_login(self, platform: str | None = None) -> str | None:
        """Account number reported by a Windows bridge EA."""
        try:
            from app.brokers.remote_mt_store import remote_mt_login

            if platform:
                login = remote_mt_login(platform)
                return str(login).strip() if login else None
            # Prefer primary mode, then whichever is online.
            for plat in (self.mode if self.mode in {"mt4", "mt5"} else None, "mt5", "mt4"):
                if not plat:
                    continue
                login = remote_mt_login(plat)
                if login:
                    return str(login).strip()
        except Exception:
            pass
        return None

    def is_mt5_client(self, account: PaperAccount | None) -> bool:
        """True only when the client explicitly linked an MT login (not paper demo)."""
        if account is None:
            return False
        want = str(getattr(account, "mt5_login", None) or "").strip()
        return want.isdigit() and 5 <= len(want) <= 16

    def is_mt_bound(self, account: PaperAccount | None) -> bool:
        """True when this JM FX client mirrors its live MT4 or MT5 terminal.

        Joel (mt_platform=mt5, login=25817283) binds only to the MT5 agent.
        An MT4-linked account binds only to the MT4 agent. Both can be always-on.
        """
        if account is None:
            return False
        if not self.is_mt5_client(account):
            return False
        plat = self.account_mt_platform(account)
        if not plat:
            return False
        bridge = self.bridge_for_account(account)
        if bridge is None or not bridge.is_online():
            return False
        want = str(getattr(account, "mt5_login", None) or "").strip()
        have = self.connected_mt_login(plat)
        return bool(have) and have == want

    def uses_paper_book(self, account: PaperAccount | None) -> bool:
        """Paper capital / fills — everyone except a live-bound MT account."""
        return not self.is_mt_bound(account) and not self.is_mt5_client(account)

    def _live_market_mid(self, symbol: str) -> float | None:
        """Live mid for paper desk sync — XAUUSD (gold) or BTCUSD (Binance)."""
        sym = (symbol or "").upper()
        if sym == "XAUUSD":
            try:
                from app.market_data.gold_feed import fetch_gold_candles

                data = fetch_gold_candles(interval="5m", limit=5)
                price = data.get("price")
                if price is None and data.get("candles"):
                    price = data["candles"][-1].get("close")
                return float(price) if price is not None else None
            except Exception:
                return None
        if sym in {"BTCUSD", "BTCUSDT"}:
            try:
                from app.market_data.crypto_feed import fetch_btc_price

                return fetch_btc_price()
            except Exception:
                return None
        return None

    # Back-compat alias
    _live_gold_mid = _live_market_mid

    def _strategy_trade_symbol(self) -> str | None:
        """Symbol this active strategy is allowed to trade (None = any/manual)."""
        if self.active_name == "manual_only":
            return None
        if self.active_name.startswith("BTC_") or self.active_name == "BTC_EMA_RSI_Scalp":
            return "BTCUSD"
        dedicated = getattr(self.strategy, "symbol", None)
        if dedicated:
            return str(dedicated).upper()
        return "XAUUSD"

    @staticmethod
    def _is_btc_symbol(symbol: str | None) -> bool:
        u = (symbol or "").upper()
        return "BTC" in u or "BITCOIN" in u

    @staticmethod
    def _is_gold_symbol(symbol: str | None) -> bool:
        u = (symbol or "").upper()
        return "XAU" in u or "GOLD" in u

    def _tick_matches_trade_symbol(
        self, tick_symbol: str | None, trade_symbol: str | None
    ) -> bool:
        """Family match so XAUUSDm/GOLD still run gold strategies (not exact string)."""
        if not trade_symbol:
            return True
        tick = (tick_symbol or "").upper()
        want = trade_symbol.upper()
        if self._is_btc_symbol(want):
            return self._is_btc_symbol(tick)
        if self._is_gold_symbol(want) or want == "XAUUSD":
            return self._is_gold_symbol(tick)
        return tick == want

    def _strategy_accepts_tick_symbol(self, strat: object, tick_symbol: str) -> bool:
        """Avoid feeding XAU M5 bars into BTC strategy history (and vice versa)."""
        name = str(getattr(strat, "name", "") or "")
        dedicated = getattr(strat, "symbol", None)
        if dedicated and self._is_btc_symbol(str(dedicated)):
            return self._is_btc_symbol(tick_symbol)
        if name.startswith("BTC_") or name == "BTC_EMA_RSI_Scalp":
            return self._is_btc_symbol(tick_symbol)
        return self._is_gold_symbol(tick_symbol)

    def _mt_bridge_live_symbol(self, platform: str | None) -> str:
        """Last symbol reported by the Windows agent for a platform."""
        plat = (platform or "").strip().lower()
        if plat not in {"mt4", "mt5"}:
            return ""
        st = get_remote_mt_state(plat)
        with st.lock:
            raw = (st.ticks_csv or "").strip()
            if raw:
                tick_sym = raw.splitlines()[-1].split(",")[0].strip().upper()
                if tick_sym:
                    return tick_sym
            return (st.symbol or "").upper()

    def _mt_bridge_supports_symbol(
        self, platform: str | None, symbol: str | None
    ) -> bool:
        """True when the live EA/agent symbol family matches the order symbol."""
        live = self._mt_bridge_live_symbol(platform)
        want = (symbol or "").upper()
        if not live or not want:
            return False
        if self._is_btc_symbol(want):
            return self._is_btc_symbol(live)
        if want in {"XAUUSD", "GOLD"} or "XAU" in want:
            return ("XAU" in live) or ("GOLD" in live)
        return live == want

    def _seed_candle_history(self) -> None:
        """Warm M1/M5 history so EMA/ADX are ready without waiting hours."""
        primary = self.settings.symbols[0]
        if self.signal_candles.closed_history(primary, 10):
            self._seed_btc_candle_history()
            return
        # Pin paper mid to live gold/BTC BEFORE seeding so EMA history sits near TV price.
        if self.settings.paper_sync_live_gold:
            self.market.pull_live_mids(force=True)
        symbol = primary
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
        self._seed_btc_candle_history()

    def _seed_btc_candle_history(self) -> None:
        """Warm BTCUSD M5 history for BTC_EMA_RSI_Scalp (paper + Binance mid)."""
        symbol = "BTCUSD"
        self.market.ensure_symbol(symbol)
        if self.signal_candles.closed_history(symbol, 10):
            return
        if self.settings.paper_sync_live_gold:
            self.market.pull_live_mids(force=True)
        mid = self.market.last_mids().get(symbol, 95000.0)
        # Prefer real Binance M5 closes when available.
        live_bars: list[Candle] = []
        try:
            from app.market_data.crypto_feed import fetch_btc_candles

            data = fetch_btc_candles(interval="5m", limit=240)
            if data.get("price"):
                mid = float(data["price"])
            for row in data.get("candles") or []:
                t = datetime.fromtimestamp(int(row["time"]), tz=timezone.utc)
                live_bars.append(
                    Candle(
                        symbol=symbol,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=1.0,
                        period_seconds=self.settings.signal_period_seconds,
                        open_time=t,
                        timestamp=t + timedelta(seconds=self.settings.signal_period_seconds - 1),
                        is_closed=True,
                    )
                )
        except Exception:
            live_bars = []

        signal_seed = max(220, int(self.settings.candle_history))
        now = utcnow()
        if len(live_bars) >= 40:
            self.signal_candles.seed_history(symbol, live_bars[-signal_seed:])
            # Lightweight M1 seed from last M5 closes
            m1: list[Candle] = []
            for b in live_bars[-min(220, len(live_bars)) :]:
                m1.append(
                    Candle(
                        symbol=symbol,
                        open=b.open,
                        high=b.high,
                        low=b.low,
                        close=b.close,
                        volume=b.volume,
                        period_seconds=self.settings.candle_period_seconds,
                        open_time=b.open_time,
                        timestamp=b.timestamp,
                        is_closed=True,
                    )
                )
            self.candles.seed_history(symbol, m1)
            self.market.sync_mid(symbol, float(live_bars[-1].close))
            return

        price = mid
        bars: list[Candle] = []
        for i in range(signal_seed):
            target = mid + math.sin(i / 11.0) * 120.0
            if i >= signal_seed - 30:
                target = mid + math.sin(i / 7.0) * 20.0
            delta = (target - price) * 0.35 + random.uniform(-8.0, 8.0)
            o = price
            c = price + delta
            h = max(o, c) + abs(delta) * 0.35 + 2.0
            l = min(o, c) - abs(delta) * 0.35 - 2.0
            open_time = now - timedelta(
                seconds=self.settings.signal_period_seconds * (signal_seed - i)
            )
            bars.append(
                Candle(
                    symbol=symbol,
                    open=round(o, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=float(20 + i % 7),
                    period_seconds=self.settings.signal_period_seconds,
                    open_time=open_time,
                    timestamp=open_time
                    + timedelta(seconds=self.settings.signal_period_seconds - 1),
                    is_closed=True,
                )
            )
            price = c
        self.signal_candles.seed_history(symbol, bars)
        self.candles.seed_history(symbol, bars)
        self.market.sync_mid(symbol, price)

    async def start(self) -> None:
        if self.running:
            return
        self._seed_candle_history()
        # Always-on desk: boot with session auto-follow whenever configured.
        if self.settings.auto_strategy:
            self.auto_enabled = True
        if self.auto_enabled:
            rec = self.recommended_now()
            target = rec.get("transfer_to") or rec.get("strategy")
            note = f"Boot session auto-follow ({rec.get('session')})"
            if not target:
                target, note = self._stand_aside_park_target(utcnow())
            if target and target in STRATEGY_REGISTRY:
                self._park_strategy(target, note=note)
                self._last_session_slot = rec.get("session")
            boot_ts = utcnow()
            self._last_hourly_transfer_at = time.time()
            self._last_transfer_hour_key = self._utc_hour_key(boot_ts)
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
        platforms = {}
        if self.bridges:
            try:
                from app.brokers.remote_mt_store import remote_snapshot_info

                platforms = {
                    "mt5": remote_snapshot_info("mt5"),
                    "mt4": remote_snapshot_info("mt4"),
                }
            except Exception:
                platforms = {}
        primary_login = self.connected_mt_login(
            self.mode if self.mode in {"mt4", "mt5"} else None
        )
        return {
            "mode": self.mode,
            "mt_configured": self.mt is not None or bool(self.bridges),
            "mt_online": self.mt_online(),
            "mt_platform": self.mode if self.mode in {"mt4", "mt5"} else self._mt_platform,
            "mt_login": primary_login,
            "bridge_dir": str(self.mt.bridge_dir) if self.mt else "",
            "using_live_feed": self.using_mt(),
            "platforms": platforms,
            "dual_bridge": bool(self.bridges),
            "paper_sync_live_gold": bool(self.settings.paper_sync_live_gold),
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

    def recommended_now(self, ts=None) -> dict:
        """Session clock + recommended session strategy."""
        when = ts or self.last_tick_at or utcnow()
        prices = self._signal_prices()
        rec = self.auto_router.recommend(when, prices)
        return {
            **rec,
            "auto_enabled": self.auto_enabled,
            "current_strategy": self.active_name,
            "display": self.active_name,
        }

    def auto_status(self) -> dict:
        decision = self.auto_router.last_decision
        rec = self.recommended_now()
        interval = max(60, int(self.settings.auto_transfer_interval_seconds))
        last_at = self._last_hourly_transfer_at or None
        # Countdown to the next UTC hour boundary (true time-session beat).
        next_in = self._seconds_to_next_utc_hour()
        return {
            "enabled": self.auto_enabled,
            "session_follow": self.auto_enabled,
            "hourly_transfer": True,
            "transfer_interval_seconds": interval,
            "last_hourly_transfer_at": last_at,
            "next_hourly_transfer_in_seconds": next_in,
            "last_transfer_hour": self._last_transfer_hour_key,
            "active_strategy": self.active_name,
            "display": self.active_name,
            "session_slot": self._last_session_slot,
            "last_transfer": self._last_transfer_note,
            "decision": decision.as_dict() if decision else None,
            "recommended": rec,
            "schedule": self.auto_router.schedule_table(),
        }

    def _utc_hour_key(self, ts) -> str:
        utc = ts.astimezone(timezone.utc)
        return utc.strftime("%Y-%m-%dT%H")

    def _seconds_to_next_utc_hour(self, ts=None) -> int:
        """Seconds until the next UTC :00 — when time-session auto-transfer runs."""
        when = ts or self.last_tick_at or utcnow()
        utc = when.astimezone(timezone.utc)
        return max(0, 3600 - (utc.minute * 60 + utc.second))

    def _hourly_transfer_due(self, ts) -> bool:
        """True on each new UTC hour — update time session + strategy map."""
        if not self.auto_enabled:
            return False
        hour_key = self._utc_hour_key(ts)
        if self._last_transfer_hour_key is None:
            return True
        return hour_key != self._last_transfer_hour_key

    async def _run_hourly_auto_transfer(self, tick: Tick) -> bool:
        """Every UTC hour: re-read time session and switch strategy if needed."""
        if not self.auto_enabled:
            return False
        if not self._hourly_transfer_due(tick.timestamp):
            return False

        previous = self.active_name
        from_slot = self._last_session_slot
        rec = self.recommended_now(tick.timestamp)
        target = rec.get("transfer_to") or rec.get("strategy")
        hour_key = self._utc_hour_key(tick.timestamp)
        hour_label = hour_key[-2:]
        stand_aside = False
        if not target:
            stand_aside = True
            target, note = self._stand_aside_park_target(tick.timestamp)
        else:
            note = (
                f"Time-session update @ {hour_label}:00 UTC → {target} "
                f"({rec.get('session')})"
            )

        switched = False
        if target and target in STRATEGY_REGISTRY:
            switched = self._park_strategy(target, note=note)
            if not switched:
                # Same strategy — still refresh the hourly note so UI shows the beat.
                self._last_transfer_note = note
            self._last_session_slot = rec.get("session")

        self._last_hourly_transfer_at = time.time()
        self._last_transfer_hour_key = hour_key

        await self._emit("engine", self.status().model_dump(mode="json"))
        await self._emit("auto", self.auto_status())
        await self._emit(
            "transfer",
            {
                "from": previous,
                "to": self.active_name,
                "from_slot": from_slot,
                "to_slot": self._last_session_slot,
                "strategy": self.active_name,
                "hour_utc": hour_key,
                "switched": switched,
                "stand_aside": stand_aside,
                "note": self._last_transfer_note,
            },
        )
        return switched

    def _park_strategy(self, name: str, *, note: str) -> bool:
        """Switch active strategy. Returns True if changed."""
        if not name:
            return False
        if name not in self._strategies:
            if name not in STRATEGY_REGISTRY:
                return False
            self._strategies[name] = create_strategy(name)
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
        ts = self.last_tick_at or utcnow()
        self._last_hourly_transfer_at = time.time()
        self._last_transfer_hour_key = self._utc_hour_key(ts)
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

        # Paper pending limits always kill at 12:00 UTC — even if MT bridges are online.
        if not is_past_pending_kill(tick.timestamp):
            return
        for acct in self.accounts.all():
            if not self.uses_paper_book(acct):
                continue
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
            # Persist immediately — auto SL/TP closes used to stay memory-only
            # and vanished on every service restart / deploy.
            self.accounts.save()
            payload = {**row.model_dump(mode="json"), "account_id": account.id}
            await self._emit("trade", payload)
            await self._emit("trades", self._trades_payload(account))

    def _journal_mode(self, account: PaperAccount | None = None) -> str:
        """Label fills by book: live mt4/mt5 when bound, else paper."""
        if account is not None and self.is_mt_bound(account):
            return self.account_mt_platform(account) or "mt5"
        if account is not None and self.is_mt5_client(account):
            return self.account_mt_platform(account) or "mt5"
        return "paper"

    async def _reconcile_mt_journal(self, tick: Tick) -> None:
        """Sync JM FX trade log to the live MT terminal (open + closed).

        Uses EA history CSV for broker PnL/exit when available. Falls back to
        last live unrealized profit (not tick.mid guess). Also corrects older
        estimated `mt_closed_synced` rows once history arrives.
        """
        for acct in self.accounts.clients():
            if not self.is_mt_bound(acct):
                continue
            bridge = self.bridge_for_account(acct)
            if bridge is None or not bridge.is_online():
                continue
            platform = self.account_mt_platform(acct) or "mt5"
            live = {p.id: p for p in bridge.open_positions()}
            history = {}
            if hasattr(bridge, "closed_history"):
                try:
                    history = bridge.closed_history() or {}
                except Exception:  # noqa: BLE001
                    history = {}
            changed = False

            # Keep open rows aligned with broker lots / entry / floating PnL.
            for live_pos in live.values():
                row = acct.journal.get_by_ticket(live_pos.id)
                if row is None or row.status != TradeStatus.OPEN:
                    continue
                before = (
                    row.unrealized_pnl,
                    row.lots,
                    row.entry,
                    row.stop_loss,
                    row.take_profit,
                    row.mode,
                )
                row.unrealized_pnl = live_pos.unrealized_pnl
                row.lots = live_pos.lots
                row.entry = live_pos.entry_price
                row.stop_loss = live_pos.stop_loss
                row.take_profit = live_pos.take_profit
                row.mode = platform
                if not row.strategy and live_pos.strategy:
                    row.strategy = live_pos.strategy
                after = (
                    row.unrealized_pnl,
                    row.lots,
                    row.entry,
                    row.stop_loss,
                    row.take_profit,
                    row.mode,
                )
                if before != after:
                    changed = True

            # Close opens that vanished on the terminal.
            for row in list(acct.journal.open_rows()):
                ticket = str(row.ticket)
                if ticket in live:
                    continue
                hist = history.get(ticket)
                entry = float(row.entry or 0.0)
                lots = float(row.lots or 0.01)
                if hist:
                    exit_px = float(hist["close_price"])
                    pnl = float(hist["profit"])
                    lots = float(hist.get("lots") or lots)
                    entry = float(hist.get("open_price") or entry)
                    reason = "mt_broker_close"
                elif row.unrealized_pnl is not None and abs(float(row.unrealized_pnl)) > 1e-9:
                    # Last floating profit from EA — far better than tick.mid guess.
                    exit_px = None
                    if row.stop_loss and abs(float(tick.mid) - float(row.stop_loss)) <= 1.5:
                        exit_px = float(row.stop_loss)
                        reason = "mt_closed_sl"
                    elif row.take_profit and abs(float(tick.mid) - float(row.take_profit)) <= 1.5:
                        exit_px = float(row.take_profit)
                        reason = "mt_closed_tp"
                    else:
                        exit_px = float(tick.mid)
                        reason = "mt_closed_synced"
                    pnl = round(float(row.unrealized_pnl), 2)
                else:
                    exit_px = float(tick.mid)
                    direction = 1.0 if row.side.value == "BUY" else -1.0
                    pnl = (
                        round(direction * (exit_px - entry) * lots * 100.0, 2)
                        if entry
                        else 0.0
                    )
                    reason = "mt_closed_estimated"

                closed = Position(
                    id=ticket,
                    symbol=row.symbol or tick.symbol,
                    side=row.side,
                    lots=lots,
                    entry_price=entry or (exit_px or float(tick.mid)),
                    stop_loss=row.stop_loss,
                    take_profit=row.take_profit,
                    strategy=row.strategy,
                    status=PositionStatus.CLOSED,
                    close_price=exit_px,
                    realized_pnl=pnl,
                    close_reason=reason,
                    closed_at=tick.timestamp,
                )
                await self._journal_close(closed, acct)
                # Force correct book label (was often stuck as "paper").
                patched = acct.journal.get_by_ticket(ticket)
                if patched is not None:
                    patched.mode = platform
                changed = True

            # Correct previously estimated closes when broker history arrives.
            for ticket, hist in history.items():
                row = acct.journal.get_by_ticket(ticket)
                if row is None or row.status != TradeStatus.CLOSED:
                    continue
                broker_pnl = round(float(hist["profit"]), 2)
                broker_exit = float(hist["close_price"])
                broker_lots = float(hist.get("lots") or row.lots or 0.01)
                broker_entry = float(hist.get("open_price") or row.entry or 0.0)
                needs = (
                    row.close_reason
                    in {
                        "mt_closed_synced",
                        "mt_closed_estimated",
                        "mt_closed_sl",
                        "mt_closed_tp",
                    }
                    or abs(float(row.realized_pnl or 0.0) - broker_pnl) > 0.05
                    or (row.exit is None)
                    or abs(float(row.exit or 0.0) - broker_exit) > 0.05
                    or row.mode != platform
                )
                if not needs:
                    continue
                acct.journal.apply_broker_close(
                    ticket,
                    exit_price=broker_exit,
                    realized_pnl=broker_pnl,
                    lots=broker_lots,
                    entry=broker_entry or None,
                    close_reason="mt_broker_close",
                    mode=platform,
                    closed_at=row.closed_at or tick.timestamp,
                )
                changed = True

            if changed:
                self.accounts.save()
                await self._emit("account", self.account_payload(acct))
                await self._emit("trades", self._trades_payload(acct))

    async def _journal_fill(
        self,
        order: Order,
        position: Position | None = None,
        *,
        signal_db_id: str | None = None,
        account: PaperAccount | None = None,
    ) -> None:
        acct = account or self._desk
        mode = self._journal_mode(acct)
        order_payload = {**order.model_dump(mode="json"), "account_id": acct.id}
        if order.status == OrderStatus.PENDING:
            await self._emit("order", order_payload)
            return
        if order.status == OrderStatus.REJECTED:
            row = acct.journal.record_order(order, mode=mode)
            self.accounts.save()
            await self._emit("trade", {**row.model_dump(mode="json"), "account_id": acct.id})
            await self._emit("trades", self._trades_payload(acct))
            return
        if position is not None:
            if order.strategy and not position.strategy:
                position.strategy = order.strategy
            row = acct.journal.record_open_position(position, mode=mode)
            self._arm_entry_cooldown()
            await self._persist_trade_open(order, position, signal_db_id=signal_db_id)
        else:
            row = acct.journal.record_order(order, mode=mode)
        self.accounts.save()
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
        snap = self.account_snapshot(acct)
        amount = float(deposit if deposit is not None else snap.deposit or snap.balance)
        risk_pct = float(self.settings.max_risk_per_trade_pct)
        daily_pct = float(self.settings.max_daily_loss_pct)
        stop_pips = float(self.settings.default_stop_loss_pips)
        tp_pips = float(self.settings.default_take_profit_pips)
        risk_usd = amount * (risk_pct / 100.0)
        daily_usd = amount * (daily_pct / 100.0) if daily_pct > 0 else None
        pip_value_per_lot = 10.0  # XAUUSD desk convention in RiskManager
        suggested = risk_usd / (stop_pips * pip_value_per_lot) if stop_pips > 0 else 0.01
        suggested_lots = max(0.01, round(suggested, 2))
        bound = self.is_mt_bound(acct)
        mt5_client = self.is_mt5_client(acct)
        return {
            "deposit": round(amount, 2) if not mt5_client or bound else 0.0,
            "currency": self.settings.base_currency,
            "paper": not mt5_client and not bound,
            "mt_bound": bound,
            "mt5_login": (acct.mt5_login or acct.code) if mt5_client else None,
            "risk_per_trade_pct": risk_pct,
            "risk_per_trade_usd": round(risk_usd, 2) if (bound or not mt5_client) else 0.0,
            "max_daily_loss_pct": daily_pct,
            "max_daily_loss_usd": round(daily_usd, 2) if daily_usd is not None else None,
            "daily_loss_limit_enabled": daily_pct > 0,
            "default_stop_loss_pips": stop_pips,
            "default_take_profit_pips": tp_pips,
            "suggested_lots": suggested_lots if (bound or not mt5_client) else 0.01,
            "account_id": acct.id,
            "presets": [100, 250, 500, 1000, 2500, 5000, 10000, 25000],
            "note": (
                "Bound to live MT — balance/equity/positions mirror the terminal"
                if bound
                else (
                    "MT account — waiting for bridge (RUN_AGENT + EA). No paper deposit."
                    if mt5_client
                    else "Paper demo capital for this account only — other clients cannot see it"
                )
            ),
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
        if self.is_mt_bound(acct) or self.is_mt5_client(acct):
            raise ValueError(
                "This account is linked to live MT5 — change deposit on the MT5 terminal, not here."
            )
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
            if self.is_mt_bound(acct) or self.is_mt5_client(acct):
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
            if self.is_mt_bound(acct):
                bridge = self.bridge_for_account(acct) or self.mt
                ack = await asyncio.to_thread(bridge.close_all)
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
            if self.is_mt5_client(acct) and not self.is_mt_bound(acct):
                return None
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
        # Always advance paper tape (includes BTCUSD) so crypto strategy stays warm.
        paper_ticks = self.market.next_ticks()
        btc_ticks = [t for t in paper_ticks if t.symbol == "BTCUSD"]
        gold_ticks = [t for t in paper_ticks if t.symbol == "XAUUSD"]

        if self.bridges:
            # Prefer MT5 ticks for the desk feed; fall back to MT4.
            for plat in ("mt5", "mt4"):
                bridge = self.bridges.get(plat)
                if bridge and bridge.is_online():
                    tick = bridge.read_tick()
                    if tick:
                        # If MT already feeds BTC, don't duplicate paper BTC.
                        if self._is_btc_symbol(tick.symbol):
                            return [tick] + gold_ticks
                        return [tick] + btc_ticks
            return paper_ticks
        if self.using_mt() and self.mt:
            tick = self.mt.read_tick()
            if tick:
                if self._is_btc_symbol(tick.symbol):
                    return [tick] + gold_ticks
                return [tick] + btc_ticks
            if self.settings.mt_remote_bridge:
                return paper_ticks
            # Local MT offline — keep full paper tape (gold + BTC), not BTC-only.
            return paper_ticks
        return paper_ticks

    async def _tick_once(self) -> None:
        async with self._lock:
            ticks = await self._next_ticks()
            for tick in ticks:
                self.ticks_processed += 1
                self.last_tick_at = tick.timestamp
                self._recent_ticks[tick.symbol] = tick

                # Hourly gold session auto-transfer — gold family ticks (XAU*/GOLD).
                if self.auto_enabled and self._is_gold_symbol(tick.symbol):
                    await self._run_hourly_auto_transfer(tick)

                # Paper books keep marking even when the MT bridge feeds ticks.
                # Bound MT5 clients mirror the terminal — skip their paper broker.
                for acct in self.accounts.all():
                    if not self.uses_paper_book(acct):
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
                # Live MT books: sync journal when terminal positions vanish.
                await self._reconcile_mt_journal(tick)
                if any(self.uses_paper_book(a) for a in self.accounts.all()):
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
                trade_sym = self._strategy_trade_symbol()
                # Gold strategy must not evaluate on BTC ticks (and vice versa).
                # Use family match so broker aliases (XAUUSDm / GOLD) still trade.
                if trade_sym and not self._tick_matches_trade_symbol(
                    tick.symbol, trade_sym
                ):
                    continue

                if closed_signal is not None:
                    # Feed M5 closes into strategies — structure / standard entries.
                    await self._persist_candle(closed_signal, timeframe="M5")
                    for strat in self._strategies.values():
                        if not self._strategy_accepts_tick_symbol(strat, tick.symbol):
                            continue
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

    async def _handle_signal(
        self,
        signal: Signal,
        tick: Tick,
        *,
        signal_db_id: str | None = None,
        london_signal_id: str | None = None,
    ) -> None:
        # Auto signals fan out per client: paper demos fill on paper; MT-bound
        # logins (Joel MT5 / Nonoy MT4) route to the Windows terminal.
        # Desk execution_mode=paper still allows live fills for bound MT accounts
        # so always-on auto strategy reaches both paper demos and live bridges.
        targets = self.accounts.auto_followers()
        if self.mode == "paper":
            targets = [
                a
                for a in targets
                if self.uses_paper_book(a) or self.is_mt_bound(a)
            ]
        # BTCUSD: paper demos always; MT-bound only when that platform's EA is on BTC.
        if self._is_btc_symbol(signal.symbol):
            filtered: list[PaperAccount] = []
            for acct in targets:
                if self.uses_paper_book(acct):
                    filtered.append(acct)
                    continue
                if not self.is_mt_bound(acct):
                    continue
                plat = self.account_mt_platform(acct)
                if self._mt_bridge_supports_symbol(plat, signal.symbol):
                    filtered.append(acct)
            targets = filtered
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
        # Multi-entry: allow more opens on a *clear* same-direction signal.
        # Still never flip/reverse an opposite open (that was the big paper-loss driver).
        opens = [
            p for p in self.open_positions(account) if p.symbol == signal.symbol
        ]
        max_open = int(self.settings.max_open_positions)
        if len(self.open_positions(account)) >= max_open:
            return
        if any(p.side != signal.side for p in opens):
            return
        if opens:
            min_strength = float(getattr(self.settings, "pyramid_min_strength", 0.90))
            if float(signal.strength or 0) < min_strength:
                return

        if (
            signal.order_type == OrderType.LIMIT
            and self.uses_paper_book(account)
            and account.broker.pending_orders()
        ):
            # One pending limit at a time; filled opens may already exist.
            return

        # Prefer per-account manual lot size (desk "Manual settings"); else micro 0.01.
        signal_lots = (
            float(account.fixed_lots)
            if account.fixed_lots is not None
            else 0.01
        )
        signal_lots = max(0.01, min(round(signal_lots, 2), 10.0))
        request = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            lots=signal_lots,
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
        if tick is not None and self.uses_paper_book(acct):
            acct.broker._last_ticks[tick.symbol] = tick
        honor_lots = bool(acct.fixed_lots is not None) or (
            (request.strategy or "").lower() == "manual"
        )
        decision = acct.risk.evaluate(
            request,
            balance=self._balance(acct),
            open_positions=self.open_positions(acct),
            tick=tick,
            honor_requested_lots=honor_lots,
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

        if self.is_mt_bound(acct):
            bridge = self.bridge_for_account(acct) or self.mt
            plat = self.account_mt_platform(acct) or getattr(bridge, "platform", None)
            if bridge and not self._mt_bridge_supports_symbol(plat, request.symbol):
                live = self._mt_bridge_live_symbol(plat) or "unknown"
                rejected = Order(
                    symbol=request.symbol,
                    side=request.side,
                    lots=request.lots,
                    strategy=request.strategy,
                    comment=request.comment,
                    status=OrderStatus.REJECTED,
                    reject_reason=(
                        f"{(plat or 'MT').upper()} EA is on {live} — "
                        f"cannot fill {request.symbol}. "
                        f"For BTC attach JM_Forex_Bridge on BTCUSD M5 + "
                        f"RUN_AGENT_MT4_BTC.bat (or gold zip for XAUUSD)."
                    ),
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
            # MT bridges are market-only — convert near LIMIT to MARKET, else reject.
            if request.order_type == OrderType.LIMIT:
                near_pips = 150.0
                strat = self._strategies.get(request.strategy or "")
                if strat is not None and hasattr(strat, "mt_near_limit_pips"):
                    try:
                        near_pips = float(strat.mt_near_limit_pips)
                    except (TypeError, ValueError):
                        pass
                pip = 0.01
                limit_px = float(request.limit_price or 0)
                mid = float(tick.mid) if tick is not None else 0.0
                dist = abs(mid - limit_px) if limit_px and mid else 1e9
                if dist <= near_pips * pip:
                    request.order_type = OrderType.MARKET
                    request.limit_price = None
                    request.expire_at = None
                    request.attach_stops = True
                    request.comment = (request.comment or "JM")[:40] + "|MT_near_limit"
                else:
                    rejected = Order(
                        symbol=request.symbol,
                        side=request.side,
                        lots=request.lots,
                        strategy=request.strategy,
                        comment=request.comment,
                        status=OrderStatus.REJECTED,
                        reject_reason=(
                            f"MT bridge has no pending LIMIT — wait until price "
                            f"within {near_pips:.0f} pips of {limit_px:.2f} "
                            f"(now dist={dist / pip:.0f} pips)"
                        ),
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
            pos = (
                self._latest_open(request.symbol, request.side, acct)
                if order.status == OrderStatus.FILLED
                else None
            )
            if pos is not None and request.strategy and not pos.strategy:
                pos.strategy = request.strategy
            # If bridge ticket is on the order but position list lags one poll, still
            # journal with strategy + live mode using the broker ticket id.
            if (
                order.status == OrderStatus.FILLED
                and pos is None
                and str(order.id).isdigit()
            ):
                mid = float(tick.mid) if tick is not None else 0.0
                pos = Position(
                    id=str(order.id),
                    symbol=request.symbol,
                    side=request.side,
                    lots=request.lots,
                    entry_price=mid,
                    stop_loss=request.stop_loss,
                    take_profit=request.take_profit,
                    strategy=request.strategy,
                    status=PositionStatus.OPEN,
                )
            await self._journal_fill(order, pos, signal_db_id=signal_db_id, account=acct)
        elif self.is_mt5_client(acct):
            # Linked MT login that is not bound to its platform — never paper-fill.
            plat = self.account_mt_platform(acct) or "mt5"
            bridge = self.bridges.get(plat) if self.bridges else None
            online = bool(bridge and bridge.is_online())
            if not online:
                reason = (
                    f"{plat.upper()} bridge offline — attach JM_Forex_Bridge EA + "
                    f"RUN_AGENT_{plat.upper()}.bat"
                )
            else:
                reason = (
                    f"This JM FX login is not bound to the connected {plat.upper()} terminal. "
                    f"Connected={self.connected_mt_login(plat) or 'unknown'} · "
                    f"your login={acct.mt5_login or acct.code}"
                )
            rejected = Order(
                symbol=request.symbol,
                side=request.side,
                lots=request.lots,
                strategy=request.strategy,
                comment=request.comment,
                status=OrderStatus.REJECTED,
                reject_reason=reason,
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
        else:
            # Paper demo — independent of global MT bridge mode.
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
