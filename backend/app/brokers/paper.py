from __future__ import annotations

from copy import deepcopy

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


class PaperBroker:
    """Simulated forex broker with instant market fills."""

    CONTRACT_SIZE = 100_000  # standard lot

    def __init__(self, initial_balance: float = 10_000.0, currency: str = "USD") -> None:
        self.balance = initial_balance
        self.currency = currency
        self.orders: list[Order] = []
        self.positions: list[Position] = []
        self._last_ticks: dict[str, Tick] = {}

    def update_tick(self, tick: Tick) -> list[Position]:
        self._last_ticks[tick.symbol] = tick
        closed: list[Position] = []
        for position in list(self.positions):
            if position.status != PositionStatus.OPEN:
                continue
            if position.symbol != tick.symbol:
                self._mark_to_market(position, tick)
                continue

            self._mark_to_market(position, tick)
            exit_price = tick.bid if position.side == Side.BUY else tick.ask

            hit_sl = False
            hit_tp = False
            if position.stop_loss is not None:
                if position.side == Side.BUY and tick.bid <= position.stop_loss:
                    hit_sl = True
                elif position.side == Side.SELL and tick.ask >= position.stop_loss:
                    hit_sl = True
            if position.take_profit is not None:
                if position.side == Side.BUY and tick.bid >= position.take_profit:
                    hit_tp = True
                elif position.side == Side.SELL and tick.ask <= position.take_profit:
                    hit_tp = True

            if hit_sl:
                closed.append(self.close_position(position.id, exit_price, "stop_loss"))
            elif hit_tp:
                closed.append(self.close_position(position.id, exit_price, "take_profit"))
        return [c for c in closed if c is not None]

    def place_order(self, request: OrderRequest) -> Order:
        tick = self._last_ticks.get(request.symbol)
        order = Order(
            symbol=request.symbol,
            side=request.side,
            lots=request.lots,
            order_type=request.order_type,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            strategy=request.strategy,
            comment=request.comment,
        )

        if tick is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"No market data for {request.symbol}"
            self.orders.append(order)
            return order

        fill = tick.ask if request.side == Side.BUY else tick.bid
        order.requested_price = fill
        order.fill_price = fill
        order.status = OrderStatus.FILLED
        order.filled_at = utcnow()
        self.orders.append(order)

        position = Position(
            symbol=request.symbol,
            side=request.side,
            lots=request.lots,
            entry_price=fill,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            strategy=request.strategy,
        )
        self.positions.append(position)
        return order

    def close_position(
        self, position_id: str, price: float | None = None, reason: str = "manual"
    ) -> Position | None:
        position = next((p for p in self.positions if p.id == position_id), None)
        if position is None or position.status != PositionStatus.OPEN:
            return None

        tick = self._last_ticks.get(position.symbol)
        if price is None:
            if tick is None:
                return None
            price = tick.bid if position.side == Side.BUY else tick.ask

        pnl = self._calc_pnl(position, price)
        position.realized_pnl = pnl
        position.unrealized_pnl = 0.0
        position.status = PositionStatus.CLOSED
        position.closed_at = utcnow()
        position.close_price = price
        position.close_reason = reason
        self.balance += pnl
        return position

    def snapshot(self) -> AccountSnapshot:
        open_positions = [p for p in self.positions if p.status == PositionStatus.OPEN]
        unrealized = sum(p.unrealized_pnl for p in open_positions)
        equity = self.balance + unrealized
        margin_used = sum(p.lots * 1000 for p in open_positions)  # simplified
        daily_pnl = unrealized + sum(
            p.realized_pnl for p in self.positions if p.status == PositionStatus.CLOSED
        )
        return AccountSnapshot(
            balance=round(self.balance, 2),
            equity=round(equity, 2),
            margin_used=round(margin_used, 2),
            free_margin=round(equity - margin_used, 2),
            open_positions=len(open_positions),
            daily_pnl=round(daily_pnl, 2),
            currency=self.currency,
        )

    def open_positions(self) -> list[Position]:
        return [deepcopy(p) for p in self.positions if p.status == PositionStatus.OPEN]

    def all_positions(self) -> list[Position]:
        return [deepcopy(p) for p in self.positions]

    def recent_orders(self, limit: int = 50) -> list[Order]:
        return [deepcopy(o) for o in self.orders[-limit:]]

    def _mark_to_market(self, position: Position, tick: Tick) -> None:
        if position.symbol != tick.symbol:
            return
        mark = tick.bid if position.side == Side.BUY else tick.ask
        position.unrealized_pnl = self._calc_pnl(position, mark)

    def _calc_pnl(self, position: Position, price: float) -> float:
        direction = 1 if position.side == Side.BUY else -1
        move = (price - position.entry_price) * direction
        return round(move * position.lots * self.CONTRACT_SIZE, 2)