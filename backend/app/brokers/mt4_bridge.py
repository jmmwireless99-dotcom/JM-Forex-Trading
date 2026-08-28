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


def _live_gold_mid() -> float | None:
    try:
        from app.market_data.gold_feed import fetch_gold_candles

        data = fetch_gold_candles(interval="5m", limit=3)
        price = data.get("price")
        if price is None and data.get("candles"):
            price = data["candles"][-1].get("close")
        mid = float(price) if price is not None else 0.0
        return mid if mid > 100 else None
    except Exception:
        return None


def repair_mt_tick_line(
    line: str,
    *,
    mt_symbol: str,
    live_mid: float | None = None,
) -> str:
    """Normalize legacy XAUUSD,0.00 ticks to configured MT symbol + live mid."""
    raw = (line or "").strip()
    if not raw:
        return line
    parts = raw.split(",")
    if len(parts) < 3:
        return line
    sym = parts[0]
    try:
        bid = float(parts[1])
        ask = float(parts[2])
    except ValueError:
        return line
    mt = (mt_symbol or "").strip()
    mt_u = mt.upper()
    sym_u = sym.upper()
    legacy = sym_u in {"XAUUSD", "XAUUSD#", "GOLD", "GOLD24-7#"}
    if legacy and mt_u and sym_u != mt_u:
        parts[0] = mt
    if bid <= 0 or ask <= 0:
        mid = live_mid if live_mid and live_mid > 100 else _live_gold_mid()
        if mid:
            spread = 0.30
            parts[1] = f"{mid - spread / 2:.2f}"
            parts[2] = f"{mid + spread / 2:.2f}"
    return ",".join(parts) + ("\n" if line.endswith("\n") else "")


def repair_mt_tick_csv(content: str, *, mt_symbol: str, live_mid: float | None = None) -> str:
    lines = [ln for ln in (content or "").splitlines() if ln.strip()]
    if not lines:
        return content or ""
    fixed = repair_mt_tick_line(lines[-1], mt_symbol=mt_symbol, live_mid=live_mid)
    return fixed if fixed.endswith("\n") else fixed + "\n"


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

    def __init__(
        self,
        bridge_dir: str | Path,
        symbol: str = "XAUUSD",
        desk_symbol: str | None = None,
    ) -> None:
        self.bridge_dir = Path(bridge_dir)
        self.mt_symbol = symbol
        self.desk_symbol = (desk_symbol or symbol).upper()
        self.symbol = self.mt_symbol.upper()
        self.command_file = self.bridge_dir / "jm_command.csv"
        self.status_file = self.bridge_dir / "jm_status.csv"
        self.positions_file = self.bridge_dir / "jm_positions.csv"
        self.tick_file = self.bridge_dir / "jm_ticks.csv"
        self.ack_file = self.bridge_dir / "jm_ack.csv"
        self.bridge_dir.mkdir(parents=True, exist_ok=True)

    def _to_mt_symbol(self, symbol: str) -> str:
        s = (symbol or "").upper()
        if s == self.desk_symbol:
            return self.mt_symbol
        return symbol

    def _to_desk_symbol(self, symbol: str) -> str:
        s = (symbol or "").upper()
        if s == self.mt_symbol.upper():
            return self.desk_symbol
        return s.upper()

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
        repaired = repair_mt_tick_line(line[-1], mt_symbol=self.mt_symbol)
        parts = repaired.strip().split(",")
        symbol, bid_s, ask_s = parts[0], parts[1], parts[2]
        bid, ask = float(bid_s), float(ask_s)
        if bid <= 0 or ask <= 0:
            return None
        desk = self._to_desk_symbol(symbol)
        decimals = 2 if desk == "XAUUSD" else 5
        return Tick(
            symbol=desk,
            bid=bid,
            ask=ask,
            mid=round((bid + ask) / 2, decimals),
        )

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
                        symbol=self._to_desk_symbol(row["symbol"]),
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
    def _format_ack_error(self, ack: BridgeAck) -> str:
        detail = (ack.detail or "").strip()
        if detail == "symbol_or_lots":
            return f"MT5 symbol mismatch — recompile EA & set InpSymbol={self.mt_symbol}"
        if detail == "timeout_waiting_mt5_ack":
            return "MT5 ack timeout — keep PC Agent open + Algo Trading ON"
        if detail.isdigit():
            return f"MT5 error {detail}"
        return detail or "MT5 bridge error"

    def place_order(self, request: OrderRequest, timeout: float = 45.0) -> Order:
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
        mt_symbol = self._to_mt_symbol(request.symbol)
        ack = self._send(
            "OPEN",
            mt_symbol,
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
            order.comment = f"mt5:{ack.detail}"
        else:
            order.status = OrderStatus.REJECTED
            order.reject_reason = self._format_ack_error(ack)
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
        return BridgeAck(cmd_id, "ERR", "timeout_waiting_mt5_ack")

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
    mt_symbol = getattr(settings, "mt_symbol", None) or getattr(settings, "mt4_symbol", "GOLD#")
    desk = settings.symbols[0] if settings.symbols else "XAUUSD"
    return MT4FileBridge(path, symbol=mt_symbol, desk_symbol=desk)
