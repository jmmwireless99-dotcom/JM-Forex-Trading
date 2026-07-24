from __future__ import annotations

import csv
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

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


@dataclass
class BridgeAck:
    command_id: str
    result: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.result.upper() == "OK"


class MT4FileBridge:
    """File-based bridge to the JM_Forex_Bridge.mq4 Expert Advisor.

    Python AI writes commands → MT4 EA executes → EA writes status/ticks/ack.

    Shared folder (typical Windows):
      C:\\Users\\<you>\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files
    Set JM_MT4_BRIDGE_DIR to that path (or a synced folder on this machine).
    """

    def __init__(self, bridge_dir: str | Path, symbol: str = "XAUUSD") -> None:
        self.bridge_dir = Path(bridge_dir)
        self.symbol = symbol.upper()
        self.command_file = self.bridge_dir / "jm_command.csv"
        self.status_file = self.bridge_dir / "jm_status.csv"
        self.positions_file = self.bridge_dir / "jm_positions.csv"
        self.tick_file = self.bridge_dir / "jm_ticks.csv"
        self.ack_file = self.bridge_dir / "jm_ack.csv"
        self.bridge_dir.mkdir(parents=True, exist_ok=True)

    # --- connectivity -------------------------------------------------
    def is_online(self, max_age_seconds: float = 5.0) -> bool:
        if not self.status_file.exists():
            return False
        age = time.time() - self.status_file.stat().st_mtime
        return age <= max_age_seconds

    def ping(self, timeout: float = 5.0) -> BridgeAck:
        return self._send("PING", timeout=timeout)

    # --- market / account ---------------------------------------------
    def read_tick(self) -> Tick | None:
        if not self.tick_file.exists():
            return None
        line = self.tick_file.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        if not line:
            return None
        parts = line[-1].split(",")
        if len(parts) < 3:
            return None
        symbol, bid_s, ask_s = parts[0], parts[1], parts[2]
        bid, ask = float(bid_s), float(ask_s)
        return Tick(symbol=symbol, bid=bid, ask=ask, mid=round((bid + ask) / 2, 5))

    def snapshot(self) -> AccountSnapshot:
        balance = equity = 0.0
        open_positions = 0
        if self.status_file.exists():
            raw = self.status_file.read_text(encoding="utf-8", errors="ignore").strip()
            parts = raw.split(",")
            # ok,balance,equity,positions,time
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
        if not self.positions_file.exists():
            return []
        rows = list(
            csv.DictReader(
                self.positions_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            )
        )
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

    # --- orders -------------------------------------------------------
    def place_order(self, request: OrderRequest, timeout: float = 8.0) -> Order:
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
            order.fill_price = None
            order.filled_at = utcnow()
            order.comment = f"mt4:{ack.detail}"
        else:
            order.status = OrderStatus.REJECTED
            order.reject_reason = ack.detail or "MT4 bridge error"
        return order

    def close_all(self, timeout: float = 8.0) -> BridgeAck:
        return self._send("CLOSE_ALL", timeout=timeout)

    # --- internals ----------------------------------------------------
    def _send(self, action: str, *fields: str, timeout: float = 5.0, command_id: str | None = None) -> BridgeAck:
        cmd_id = command_id or uuid.uuid4().hex[:12]
        # clear old ack so we don't read a stale one
        if self.ack_file.exists():
            try:
                self.ack_file.unlink()
            except OSError:
                pass

        row = ",".join([cmd_id, action, *fields])
        # header + single command (EA processes all non-header lines)
        payload = "id,action,symbol,side,lots,sl,tp,comment\n" + row + "\n"
        tmp = self.command_file.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.command_file)

        deadline = time.time() + timeout
        while time.time() < deadline:
            ack = self._read_ack()
            if ack and ack.command_id == cmd_id:
                return ack
            time.sleep(0.15)
        return BridgeAck(cmd_id, "ERR", "timeout_waiting_mt4_ack")

    def _read_ack(self) -> BridgeAck | None:
        if not self.ack_file.exists():
            return None
        raw = self.ack_file.read_text(encoding="utf-8", errors="ignore").strip()
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


def resolve_bridge(settings) -> MT4FileBridge | None:
    path = getattr(settings, "mt4_bridge_dir", "") or ""
    if not path:
        return None
    return MT4FileBridge(path, symbol=settings.symbols[0] if settings.symbols else "XAUUSD")
