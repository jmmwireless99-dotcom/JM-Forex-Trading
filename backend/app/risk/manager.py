from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.models.domain import OrderRequest, Position, PositionStatus, Side, Tick


@dataclass
class RiskDecision:
    approved: bool
    reason: str = ""
    adjusted_lots: float | None = None


class RiskManager:
    """Hard risk gates before any order reaches the broker."""

    PIP_SIZES = {
        "USDJPY": 0.01,
        "XAUUSD": 0.1,
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._daily_realized_pnl = 0.0
        self._starting_balance = settings.initial_balance

    def reset_daily(self, balance: float) -> None:
        self._daily_realized_pnl = 0.0
        self._starting_balance = balance

    def record_realized_pnl(self, pnl: float) -> None:
        self._daily_realized_pnl += pnl

    def daily_loss_hit(self) -> bool:
        """True once today's realized loss hits max_daily_loss_pct (0 = disabled).

        Shared gate used for every paper account type — including scale-in
        books, which bypass RiskManager.evaluate() for their own position
        sizing but must still respect the same capital-protection circuit
        breaker.
        """
        if self.settings.max_daily_loss_pct <= 0:
            return False
        max_daily_loss = self._starting_balance * (
            self.settings.max_daily_loss_pct / 100.0
        )
        return self._daily_realized_pnl <= -max_daily_loss

    def pip_size(self, symbol: str) -> float:
        return self.PIP_SIZES.get(symbol.upper(), 0.0001)

    def evaluate(
        self,
        request: OrderRequest,
        *,
        balance: float,
        open_positions: list[Position],
        tick: Tick | None,
    ) -> RiskDecision:
        opens = [p for p in open_positions if p.status == PositionStatus.OPEN]

        if request.lots <= 0:
            return RiskDecision(False, "Lot size must be positive")

        if len(opens) >= self.settings.max_open_positions:
            return RiskDecision(
                False,
                f"Max open positions reached ({self.settings.max_open_positions})",
            )

        same_symbol = [p for p in opens if p.symbol == request.symbol]
        if same_symbol:
            return RiskDecision(False, f"Already have an open position on {request.symbol}")

        # Daily loss kill-switch (disabled when max_daily_loss_pct <= 0)
        if self.daily_loss_hit():
            return RiskDecision(
                False,
                f"Daily loss limit hit ({self.settings.max_daily_loss_pct}%)",
            )

        # Position sizing from risk % and stop distance
        stop_pips = self.settings.default_stop_loss_pips
        if request.stop_loss and tick:
            entry = tick.ask if request.side == Side.BUY else tick.bid
            stop_pips = abs(entry - request.stop_loss) / self.pip_size(request.symbol)

        if stop_pips <= 0:
            return RiskDecision(False, "Invalid stop loss distance")

        risk_amount = balance * (self.settings.max_risk_per_trade_pct / 100.0)
        # $ value of 1 pip on 1.0 lot
        # FX majors ≈ $10/pip; XAUUSD pip=0.1 → $10/pip on 100oz lot
        pip_value_per_lot = 10.0
        max_lots = risk_amount / (stop_pips * pip_value_per_lot)
        # Gold: allow micro sizing down to 0.01
        max_lots = max(0.01, round(min(max_lots, request.lots), 2))

        if max_lots < 0.01:
            return RiskDecision(False, "Calculated lot size below minimum 0.01")

        return RiskDecision(True, "Approved", adjusted_lots=max_lots)

    def apply_default_stops(
        self, request: OrderRequest, tick: Tick
    ) -> tuple[float | None, float | None]:
        pip = self.pip_size(request.symbol)
        entry = tick.ask if request.side == Side.BUY else tick.bid
        sl_pips = self.settings.default_stop_loss_pips
        tp_pips = self.settings.default_take_profit_pips

        if request.side == Side.BUY:
            sl = request.stop_loss or (entry - sl_pips * pip)
            tp = request.take_profit or (entry + tp_pips * pip)
        else:
            sl = request.stop_loss or (entry + sl_pips * pip)
            tp = request.take_profit or (entry - tp_pips * pip)
        return sl, tp

    def stops_from_entry(
        self,
        *,
        symbol: str,
        side: Side,
        entry: float,
        stop_loss_pips: float | None = None,
        take_profit_pips: float | None = None,
    ) -> tuple[float, float]:
        """Build SL/TP prices from entry + pip distances (manual / post-open)."""
        pip = self.pip_size(symbol)
        sl_pips = (
            stop_loss_pips
            if stop_loss_pips is not None
            else self.settings.default_stop_loss_pips
        )
        tp_pips = (
            take_profit_pips
            if take_profit_pips is not None
            else self.settings.default_take_profit_pips
        )
        if side == Side.BUY:
            return entry - sl_pips * pip, entry + tp_pips * pip
        return entry + sl_pips * pip, entry - tp_pips * pip