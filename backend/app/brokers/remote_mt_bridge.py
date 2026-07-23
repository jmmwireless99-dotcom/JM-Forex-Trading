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


class RemoteMetaTraderBridge:
    """Same behavior as MT4FileBridge, but state comes from the Windows agent."""

    def __init__(self, symbol: str = "XAUUSD") -> None:
        self.symbol = (symbol or "XAUUSD").upper()
        self.bridge_dir = Path("remote://windows-agent")

    def is_online(self, max_age_seconds: float = 8.0) -> bool:
        return remote_is_online(max_age_seconds=max_age_seconds)

    def ping(self, timeout: float = 8.0) -> BridgeAck:
        return self._send("PING", timeout=timeout)

    def read_tick(self) -> Tick | None:
        st = get_remote_mt_state()
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
        st = get_remote_mt_state()
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
        st = get_remote_mt_state()
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

    def place_order(self, request: OrderRequest, timeout: float = 12.0) -> Order:
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
            order.comment = f"mt5:{ack.detail}"
        else:
            order.status = OrderStatus.REJECTED
            order.reject_reason = ack.detail or "MT remote bridge error"
        return order

    def close_all(self, timeout: float = 12.0) -> BridgeAck:
        return self._send("CLOSE_ALL", timeout=timeout)

    def _send(
        self,
        action: str,
        *fields: str,
        timeout: float = 8.0,
        command_id: str | None = None,
    ) -> BridgeAck:
        if not self.is_online():
            return BridgeAck(
                command_id or "none",
                "ERR",
                "windows_agent_offline — run jm_mt_agent.py on the MT5 PC",
            )
        cmd_id = command_id or uuid.uuid4().hex[:12]
        row = ",".join([cmd_id, action, *fields])
        payload = "id,action,symbol,side,lots,sl,tp,comment\n" + row + "\n"
        remote_set_command(cmd_id, payload)

        deadline = time.time() + timeout
        while time.time() < deadline:
            ack = self._read_ack()
            if ack and ack.command_id == cmd_id:
                remote_clear_command(cmd_id)
                return ack
            time.sleep(0.2)
        remote_clear_command(cmd_id)
        return BridgeAck(cmd_id, "ERR", "timeout_waiting_mt5_ack")

    def _read_ack(self) -> BridgeAck | None:
        st = get_remote_mt_state()
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
