"""Remote MetaTrader bridge — cloud AI talks to a Windows agent over HTTP."""

from __future__ import annotations

import csv
import io
import time
import uuid
from pathlib import Path

from app.brokers.mt4_bridge import BridgeAck
from app.brokers.remote_mt_store import (
    get_remote_mt_state,
    normalize_platform,
    remote_clear_command,
    remote_is_online,
    remote_set_command,
)
from app.models.domain import (
    AccountSnapshot,
    Order,
    OrderRequest,
    OrderStatus,
    Position,
    PositionStatus,
    Side,
    Tick,
    utcnow,
)


def _humanize_mt_error(detail: str | None) -> str:
    """Map bare MT4/MT5 codes / EA tags to actionable reject text."""
    raw = (detail or "").strip()
    if not raw:
        return "MT remote bridge error"
    key = raw.lower()
    mapping = {
        "4752": "Algo Trading OFF — i-ON ang Algo Trading sa MT5 toolbar + EA Allow Algo Trading",
        "4109": "AutoTrading OFF — i-ON ang AutoTrading sa MT4 toolbar + EA Allow live trading",
        "10027": "Algo Trading OFF — enable MT5 Algo Trading (toolbar green)",
        "algotrading_off_enable_toolbar_and_ea_allow_algo_trading": (
            "Algo Trading OFF — i-ON ang Algo Trading sa MT5 + EA Allow Algo Trading"
        ),
        "autotrading_off_enable_toolbar_and_ea_allow_live_trading": (
            "AutoTrading OFF — i-ON ang AutoTrading sa MT4 + EA Allow live trading"
        ),
        "autotrading_toolbar_off_click_autotrading_green": (
            "MT4 AutoTrading toolbar OFF — click AutoTrading until GREEN, then re-attach EA"
        ),
        "algotrading_toolbar_off_click_algo_trading_green": (
            "MT5 Algo Trading toolbar OFF — click Algo Trading until GREEN"
        ),
        "ea_allow_algo_trading_unchecked_reattach_ea": (
            "EA Allow Algo Trading OFF — F7 → check Allow Algo Trading → OK (re-attach if needed)"
        ),
        "autotrading_toolbar_off_or_ea_allow_live_trading": (
            "MT4 still blocks EA trades — toggle AutoTrading OFF/ON, re-attach EA, Allow live trading"
        ),
        "algotrading_toolbar_off_or_ea_allow_algo_trading": (
            "MT5 still blocks EA trades — toggle Algo Trading OFF/ON, re-attach EA, Allow Algo Trading"
        ),
        "trade_not_allowed_check_ea_allow_live_trading_and_account": (
            "Trade not allowed — EA Allow live trading + Tools→Options→Expert Advisors→Allow automated trading"
        ),
        "account_trading_disabled_by_broker": "Broker disabled trading on this account",
        "account_blocks_expert_advisors": "This account blocks Expert Advisors — ask broker to enable EA trading",
        "symbol_trade_disabled_or_market_closed": (
            "XAUUSD not tradeable right now (market closed / symbol disabled)"
        ),
        "terminal_not_connected": "Terminal not connected to broker",
        "trade_context_busy_retry": "Trade context busy — click Buy again",
        "invalid_stops": "Invalid SL/TP — stops too close to price (broker stop level)",
        "not_enough_money": "Not enough free margin for this lot size",
        "off_quotes": "No quotes / market closed — check symbol XAUUSD",
        "symbol_or_lots": "Symbol mismatch or invalid lots — EA InpSymbol must be XAUUSD",
        "symbol_mismatch": "Symbol mismatch — EA chart symbol must match XAUUSD",
    }
    if key in mapping:
        return mapping[key]
    if key.startswith("error_") and key[6:].isdigit():
        return mapping.get(key[6:], raw) if key[6:] in mapping else raw
    if key.startswith("retcode_") and key[8:] in mapping:
        return mapping[key[8:]]
    if raw.isdigit() and raw in mapping:
        return mapping[raw]
    return raw


class RemoteMetaTraderBridge:
    """Same behavior as MT4FileBridge, but state comes from the Windows agent."""

    def __init__(self, symbol: str = "XAUUSD", platform: str = "mt5") -> None:
        self.symbol = (symbol or "XAUUSD").upper()
        self.platform = normalize_platform(platform)
        self.bridge_dir = Path(f"remote://windows-agent/{self.platform}")

    def is_online(self, max_age_seconds: float = 8.0) -> bool:
        return remote_is_online(
            max_age_seconds=max_age_seconds, platform=self.platform
        )

    def ping(self, timeout: float = 25.0) -> BridgeAck:
        return self._send("PING", timeout=timeout)

    def read_tick(self) -> Tick | None:
        st = get_remote_mt_state(self.platform)
        with st.lock:
            raw = st.ticks_csv.strip()
        if not raw:
            return None
        line = raw.splitlines()[-1]
        parts = line.split(",")
        if len(parts) < 3:
            return None
        symbol, bid_s, ask_s = parts[0], parts[1], parts[2]
        bid, ask = float(bid_s), float(ask_s)
        return Tick(symbol=symbol, bid=bid, ask=ask, mid=round((bid + ask) / 2, 5))

    def snapshot(self) -> AccountSnapshot:
        balance = equity = 0.0
        open_positions = 0
        st = get_remote_mt_state(self.platform)
        with st.lock:
            raw = st.status_csv.strip()
        if raw:
            parts = raw.split(",")
            if len(parts) >= 4:
                balance = float(parts[1])
                equity = float(parts[2])
                open_positions = int(float(parts[3]))
        return AccountSnapshot(
            balance=balance,
            equity=equity,
            margin_used=0.0,
            free_margin=equity,
            open_positions=open_positions,
            daily_pnl=round(equity - balance, 2),
            currency="USD",
            deposit=balance,
            paper=False,
        )

    def open_positions(self) -> list[Position]:
        st = get_remote_mt_state(self.platform)
        with st.lock:
            raw = st.positions_csv.strip()
        if not raw:
            return []
        rows = list(csv.DictReader(io.StringIO(raw)))
        positions: list[Position] = []
        for row in rows:
            try:
                positions.append(
                    Position(
                        id=str(row["ticket"]),
                        symbol=row["symbol"],
                        side=Side(row["side"]),
                        lots=float(row["lots"]),
                        entry_price=float(row["open_price"]),
                        stop_loss=float(row["sl"]) if float(row["sl"]) else None,
                        take_profit=float(row["tp"]) if float(row["tp"]) else None,
                        unrealized_pnl=float(row["profit"]),
                        status=PositionStatus.OPEN,
                    )
                )
            except (KeyError, ValueError):
                continue
        return positions

    def closed_history(self) -> dict[str, dict]:
        """Parse EA history CSV → ticket → broker close facts.

        CSV header:
        ticket,symbol,side,lots,open_price,close_price,sl,tp,profit,close_time
        """
        st = get_remote_mt_state(self.platform)
        with st.lock:
            raw = st.history_csv.strip()
        if not raw:
            return {}
        out: dict[str, dict] = {}
        for row in csv.DictReader(io.StringIO(raw)):
            try:
                ticket = str(row.get("ticket") or "").strip()
                if not ticket:
                    continue
                out[ticket] = {
                    "ticket": ticket,
                    "symbol": row.get("symbol") or self.symbol,
                    "side": row.get("side"),
                    "lots": float(row["lots"]),
                    "open_price": float(row["open_price"]),
                    "close_price": float(row["close_price"]),
                    "sl": float(row["sl"]) if row.get("sl") else 0.0,
                    "tp": float(row["tp"]) if row.get("tp") else 0.0,
                    "profit": float(row["profit"]),
                    "close_time": (row.get("close_time") or "").strip(),
                }
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def place_order(self, request: OrderRequest, timeout: float = 25.0) -> Order:
        order = Order(
            symbol=request.symbol,
            side=request.side,
            lots=request.lots,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            strategy=request.strategy,
            comment=request.comment or "JM",
        )
        sl = "" if request.stop_loss is None else f"{request.stop_loss:.5f}"
        tp = "" if request.take_profit is None else f"{request.take_profit:.5f}"
        comment = (request.comment or "JM").replace(",", " ")
        ack = self._send(
            "OPEN",
            request.symbol,
            request.side.value,
            f"{request.lots:.2f}",
            sl,
            tp,
            comment,
            timeout=timeout,
            command_id=order.id[:12],
        )
        if ack.ok:
            order.status = OrderStatus.FILLED
            order.filled_at = utcnow()
            # Prefer broker ticket from EA ack detail when present.
            detail = (ack.detail or "").strip()
            if detail.isdigit():
                order.id = detail
            order.comment = f"{self.platform}:{detail or 'filled'}"
        else:
            order.status = OrderStatus.REJECTED
            order.reject_reason = _humanize_mt_error(ack.detail) or "MT remote bridge error"
        return order

    def close_all(self, timeout: float = 25.0) -> BridgeAck:
        return self._send("CLOSE_ALL", timeout=timeout)

    def _send(
        self,
        action: str,
        *fields: str,
        timeout: float = 25.0,
        command_id: str | None = None,
    ) -> BridgeAck:
        if not self.is_online():
            return BridgeAck(
                command_id or "none",
                "ERR",
                f"windows_agent_offline — run agent for {self.platform}",
            )
        cmd_id = command_id or uuid.uuid4().hex[:12]
        row = ",".join([cmd_id, action, *fields])
        payload = "id,action,symbol,side,lots,sl,tp,comment\n" + row + "\n"
        remote_set_command(cmd_id, payload, platform=self.platform)

        deadline = time.time() + timeout
        while time.time() < deadline:
            ack = self._read_ack()
            if ack and ack.command_id == cmd_id:
                remote_clear_command(cmd_id, platform=self.platform)
                return ack
            # Caller must run this in a worker thread (asyncio.to_thread) so the
            # Windows agent can still POST /mt/remote/push with the EA ack.
            time.sleep(0.15)
        remote_clear_command(cmd_id, platform=self.platform)
        return BridgeAck(cmd_id, "ERR", f"timeout_waiting_{self.platform}_ack")

    def _read_ack(self) -> BridgeAck | None:
        st = get_remote_mt_state(self.platform)
        with st.lock:
            raw = st.ack_csv.strip()
        if not raw:
            return None
        parts = raw.split(",")
        if len(parts) < 2:
            return None
        return BridgeAck(
            command_id=parts[0],
            result=parts[1],
            detail=parts[2] if len(parts) > 2 else "",
        )
