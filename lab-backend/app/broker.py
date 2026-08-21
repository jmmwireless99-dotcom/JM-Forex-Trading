from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def _now() -> datetime:
    return datetime.now(timezone.utc)


Side = Literal["BUY", "SELL"]


@dataclass
class Position:
    id: str
    symbol: str
    side: Side
    lots: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    unrealized_pnl: float = 0.0
    realized_pnl: float | None = None
    opened_at: str = field(default_factory=lambda: _now().isoformat())
    closed_at: str | None = None
    close_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "lots": self.lots,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "status": self.status,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "realized_pnl": self.realized_pnl,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "close_reason": self.close_reason,
        }


class LabBroker:
    """Minimal FX paper broker for lab experiments."""

    CONTRACT = 100_000  # standard FX lot
    SPREAD_PIPS = {"EURUSD": 0.8, "GBPUSD": 1.0, "XAUUSD": 0.25, "AUDNZD": 1.2, "EURCHF": 1.0}

    def __init__(self, deposit: float = 10_000.0, currency: str = "USD") -> None:
        self.deposit = round(float(deposit), 2)
        self.balance = round(float(deposit), 2)
        self.currency = currency
        self.positions: list[Position] = []
        self.trades: list[dict[str, Any]] = []
        self._ticks: dict[str, dict[str, float]] = {}

    def equity(self) -> float:
        upnl = sum(p.unrealized_pnl for p in self.positions if p.status == "OPEN")
        return round(self.balance + upnl, 2)

    def daily_pnl(self) -> float:
        return round(self.equity() - self.deposit, 2)

    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.status == "OPEN"]

    def _pip(self, symbol: str) -> float:
        return 0.01 if symbol == "XAUUSD" else 0.0001

    def _half_spread(self, symbol: str) -> float:
        return self._pip(symbol) * self.SPREAD_PIPS.get(symbol, 1.0) / 2

    def entry_price(self, symbol: str, side: Side, mid: float) -> float:
        """Expected fill from mid (ask for BUY, bid for SELL)."""
        hs = self._half_spread(symbol)
        px = mid + hs if side == "BUY" else mid - hs
        return round(px, 2 if symbol == "XAUUSD" else 5)

    def update_tick(self, symbol: str, mid: float) -> list[Position]:
        hs = self._half_spread(symbol)
        self._ticks[symbol] = {"mid": mid, "bid": mid - hs, "ask": mid + hs}
        closed: list[Position] = []
        for p in list(self.positions):
            if p.status != "OPEN" or p.symbol != symbol:
                continue
            tick = self._ticks[symbol]
            bid, ask = tick["bid"], tick["ask"]
            p.unrealized_pnl = self._pnl(p, bid if p.side == "BUY" else ask)
            exit_px = None
            reason = None
            if p.side == "BUY":
                if p.stop_loss is not None and bid <= p.stop_loss:
                    exit_px, reason = p.stop_loss, "stop_loss"
                elif p.take_profit is not None and bid >= p.take_profit:
                    exit_px, reason = p.take_profit, "take_profit"
            else:
                if p.stop_loss is not None and ask >= p.stop_loss:
                    exit_px, reason = p.stop_loss, "stop_loss"
                elif p.take_profit is not None and ask <= p.take_profit:
                    exit_px, reason = p.take_profit, "take_profit"
            if exit_px is not None:
                c = self.close_position(p.id, exit_px, reason or "close")
                if c:
                    closed.append(c)
        return closed

    def _pnl(self, p: Position, mark: float) -> float:
        diff = mark - p.entry_price if p.side == "BUY" else p.entry_price - mark
        mult = self.CONTRACT if p.symbol != "XAUUSD" else 100
        return round(diff * p.lots * mult, 2)

    def open_market(
        self,
        *,
        symbol: str,
        side: Side,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Position:
        if lots <= 0 or lots > 50:
            raise ValueError("Lots must be between 0.01 and 50")
        tick = self._ticks.get(symbol)
        if not tick:
            raise ValueError(f"No live price for {symbol}")
        if any(p.status == "OPEN" for p in self.positions):
            raise ValueError("Close open position first (lab max 1 open)")
        entry = tick["ask"] if side == "BUY" else tick["bid"]
        pos = Position(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=side,
            lots=round(lots, 2),
            entry_price=round(entry, 5 if symbol != "XAUUSD" else 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        pos.unrealized_pnl = 0.0
        self.positions.append(pos)
        return pos

    def _round_price(self, symbol: str, price: float) -> float:
        digits = 2 if symbol == "XAUUSD" else 5
        return round(price, digits)

    def update_stops(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        clear_stop_loss: bool = False,
        clear_take_profit: bool = False,
    ) -> Position | None:
        for p in self.positions:
            if p.id != position_id or p.status != "OPEN":
                continue
            entry = p.entry_price
            new_sl = None if clear_stop_loss else (stop_loss if stop_loss is not None else p.stop_loss)
            new_tp = None if clear_take_profit else (take_profit if take_profit is not None else p.take_profit)
            if new_sl is not None:
                new_sl = self._round_price(p.symbol, float(new_sl))
            if new_tp is not None:
                new_tp = self._round_price(p.symbol, float(new_tp))
            if p.side == "BUY":
                if new_sl is not None and new_sl >= entry:
                    raise ValueError("BUY stop loss must be below entry")
                if new_tp is not None and new_tp <= entry:
                    raise ValueError("BUY take profit must be above entry")
            else:
                if new_sl is not None and new_sl <= entry:
                    raise ValueError("SELL stop loss must be above entry")
                if new_tp is not None and new_tp >= entry:
                    raise ValueError("SELL take profit must be below entry")
            p.stop_loss = new_sl
            p.take_profit = new_tp
            return p
        return None

    def close_position(
        self, position_id: str, exit_price: float | None = None, reason: str = "manual"
    ) -> Position | None:
        for p in self.positions:
            if p.id != position_id or p.status != "OPEN":
                continue
            tick = self._ticks.get(p.symbol)
            if exit_price is None:
                if not tick:
                    return None
                exit_price = tick["bid"] if p.side == "BUY" else tick["ask"]
            pnl = self._pnl(p, exit_price)
            p.status = "CLOSED"
            p.realized_pnl = pnl
            p.unrealized_pnl = 0.0
            p.closed_at = _now().isoformat()
            p.close_reason = reason
            self.balance = round(self.balance + pnl, 2)
            self.trades.insert(
                0,
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "side": p.side,
                    "lots": p.lots,
                    "entry_price": p.entry_price,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                    "exit_price": round(exit_price, 5 if p.symbol != "XAUUSD" else 2),
                    "pnl": pnl,
                    "reason": reason,
                    "closed_at": p.closed_at,
                },
            )
            return p
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "deposit": self.deposit,
            "balance": self.balance,
            "currency": self.currency,
            "positions": [p.to_dict() for p in self.positions],
            "trades": deepcopy(self.trades),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabBroker:
        b = cls(deposit=data.get("deposit", 10_000), currency=data.get("currency", "USD"))
        b.balance = float(data.get("balance", b.deposit))
        for row in data.get("positions") or []:
            b.positions.append(
                Position(
                    id=row["id"],
                    symbol=row["symbol"],
                    side=row["side"],
                    lots=float(row["lots"]),
                    entry_price=float(row["entry_price"]),
                    stop_loss=row.get("stop_loss"),
                    take_profit=row.get("take_profit"),
                    status=row.get("status", "OPEN"),
                    unrealized_pnl=float(row.get("unrealized_pnl") or 0),
                    realized_pnl=row.get("realized_pnl"),
                    opened_at=row.get("opened_at") or _now().isoformat(),
                    closed_at=row.get("closed_at"),
                    close_reason=row.get("close_reason"),
                )
            )
        b.trades = list(data.get("trades") or [])
        return b
