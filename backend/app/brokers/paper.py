from __future__ import annotations

from copy import deepcopy

from app.models.domain import (
    AccountSnapshot,
    Order,
    OrderRequest,
    OrderStatus,
    OrderType,
    Position,
    PositionStatus,
    Side,
    Tick,
    utcnow,
)


class PaperBroker:
    """Simulated forex broker with instant market fills."""

    # Contract size per 1.0 lot
    CONTRACT_SIZES = {
        "XAUUSD": 100,  # 100 oz — $1 move ≈ $100 / lot
    }
    DEFAULT_CONTRACT_SIZE = 100_000  # FX standard lot

    def __init__(self, initial_balance: float = 10_000.0, currency: str = "USD") -> None:
        self.balance = initial_balance
        self.currency = currency
        self.orders: list[Order] = []
        self.positions: list[Position] = []
        self._last_ticks: dict[str, Tick] = {}

    def update_tick(self, tick: Tick) -> list[Position]:
        self._last_ticks[tick.symbol] = tick
        # Fill pending LIMIT orders first
        self._try_fill_limits(tick)
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

    def _try_fill_limits(self, tick: Tick) -> None:
        now = tick.timestamp
        for order in self.orders:
            if order.status != OrderStatus.PENDING or order.order_type != OrderType.LIMIT:
                continue
            if order.symbol != tick.symbol or order.limit_price is None:
                continue
            if order.expire_at is not None and now >= order.expire_at:
                order.status = OrderStatus.CANCELLED
                order.reject_reason = "Limit expired (London 12:00 UTC kill switch)"
                continue
            hit = False
            if order.side == Side.BUY and tick.ask <= order.limit_price:
                hit = True
                fill = min(tick.ask, order.limit_price)
            elif order.side == Side.SELL and tick.bid >= order.limit_price:
                hit = True
                fill = max(tick.bid, order.limit_price)
            if not hit:
                continue
            order.fill_price = fill
            order.status = OrderStatus.FILLED
            order.filled_at = utcnow()
            self.positions.append(
                Position(
                    symbol=order.symbol,
                    side=order.side,
                    lots=order.lots,
                    entry_price=fill,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    strategy=order.strategy,
                )
            )

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
            limit_price=request.limit_price,
            expire_at=request.expire_at,
            requested_price=request.limit_price,
        )

        if tick is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"No market data for {request.symbol}"
            self.orders.append(order)
            return order

        if request.order_type == OrderType.LIMIT:
            if request.limit_price is None:
                order.status = OrderStatus.REJECTED
                order.reject_reason = "LIMIT order requires limit_price"
                self.orders.append(order)
                return order
            # Immediate fill if already through price
            if request.side == Side.BUY and tick.ask <= request.limit_price:
                fill = tick.ask
                order.fill_price = fill
                order.status = OrderStatus.FILLED
                order.filled_at = utcnow()
                self.orders.append(order)
                self.positions.append(
                    Position(
                        symbol=request.symbol,
                        side=request.side,
                        lots=request.lots,
                        entry_price=fill,
                        stop_loss=request.stop_loss,
                        take_profit=request.take_profit,
                        strategy=request.strategy,
                    )
                )
                return order
            if request.side == Side.SELL and tick.bid >= request.limit_price:
                fill = tick.bid
                order.fill_price = fill
                order.status = OrderStatus.FILLED
                order.filled_at = utcnow()
                self.orders.append(order)
                self.positions.append(
                    Position(
                        symbol=request.symbol,
                        side=request.side,
                        lots=request.lots,
                        entry_price=fill,
                        stop_loss=request.stop_loss,
                        take_profit=request.take_profit,
                        strategy=request.strategy,
                    )
                )
                return order
            order.status = OrderStatus.PENDING
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

    def pending_orders(self) -> list[Order]:
        return [
            deepcopy(o)
            for o in self.orders
            if o.status == OrderStatus.PENDING and o.order_type == OrderType.LIMIT
        ]

    def cancel_pending(self, *, reason: str = "cancelled") -> list[Order]:
        out: list[Order] = []
        for order in self.orders:
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                order.reject_reason = reason
                out.append(deepcopy(order))
        return out

    def set_stops(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Position | None:
        """Attach or update SL/TP on an open position."""
        position = next((p for p in self.positions if p.id == position_id), None)
        if position is None or position.status != PositionStatus.OPEN:
            return None
        if stop_loss is not None:
            position.stop_loss = stop_loss
        if take_profit is not None:
            position.take_profit = take_profit
        return position

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
        # Simplified margin: gold ~$500/lot notionally scaled; FX ~$1000/lot
        margin_used = sum(
            p.lots * (500 if p.symbol.upper() == "XAUUSD" else 1000) for p in open_positions
        )
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

    def contract_size(self, symbol: str) -> float:
        return self.CONTRACT_SIZES.get(symbol.upper(), self.DEFAULT_CONTRACT_SIZE)

    def _calc_pnl(self, position: Position, price: float) -> float:
        direction = 1 if position.side == Side.BUY else -1
        move = (price - position.entry_price) * direction
        return round(move * position.lots * self.contract_size(position.symbol), 2)