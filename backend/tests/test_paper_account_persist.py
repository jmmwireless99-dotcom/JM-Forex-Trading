"""Paper account journal must survive restart without rewriting history."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.models.domain import Position, PositionStatus, Side, TradeLog, TradeStatus, utcnow
from app.paper_accounts.registry import PaperAccountRegistry


def test_open_trades_restore_on_reload(tmp_path: Path) -> None:
    store = tmp_path / "paper_accounts.json"
    settings = Settings()
    reg = PaperAccountRegistry(settings, store_path=store)
    acc = reg.create(deposit=1000, label="PersistTest")

    opened = utcnow()
    ticket = "pos-persist-1"
    acc.journal._trades.appendleft(
        TradeLog(
            ticket=ticket,
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            entry=4120.5,
            stop_loss=4100.0,
            take_profit=4150.0,
            status=TradeStatus.OPEN,
            strategy="Liquidity_Sweep_SMC",
            opened_at=opened,
            unrealized_pnl=3.2,
        )
    )
    acc.journal._by_ticket[ticket] = acc.journal._trades[0]
    acc.broker.positions.append(
        Position(
            id=ticket,
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            entry_price=4120.5,
            stop_loss=4100.0,
            take_profit=4150.0,
            strategy="Liquidity_Sweep_SMC",
            status=PositionStatus.OPEN,
            unrealized_pnl=3.2,
            opened_at=opened,
        )
    )
    reg.save()

    reg2 = PaperAccountRegistry(settings, store_path=store)
    loaded = reg2.get(acc.id)
    assert loaded is not None
    rows = loaded.journal.list(10)
    assert len(rows) == 1
    assert rows[0].status == TradeStatus.OPEN
    assert rows[0].close_reason is None
    assert rows[0].entry == 4120.5
    assert abs((rows[0].opened_at - opened).total_seconds()) < 1
    opens = loaded.broker.open_positions()
    assert len(opens) == 1
    assert opens[0].id == ticket
    assert opens[0].entry_price == 4120.5
