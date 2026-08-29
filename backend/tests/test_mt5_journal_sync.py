"""Tests for DDDC3D MT5 ↔ JM FX journal mirroring."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.brokers.mt4_bridge import MT4FileBridge
from app.core.config import Settings
from app.engine.mt5_journal_sync import (
    parse_mt5_ticket,
    sync_journal_with_mt5,
    wait_mt_position,
)
from app.engine.trade_journal import TradeJournal
from app.models.domain import Order, OrderStatus, OrderRequest, Position, Side, TradeStatus
from app.paper_accounts.registry import PaperAccountRegistry


def test_parse_mt5_ticket_from_order_comment():
    order = Order(
        symbol="XAUUSD",
        side=Side.BUY,
        lots=0.01,
        comment="mt5:123456",
        status=OrderStatus.FILLED,
    )
    assert parse_mt5_ticket(order) == "123456"


def test_sync_journal_updates_open_row_from_mt5_position():
    journal = TradeJournal()
    journal.record_order(
        Order(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            fill_price=None,
            comment="mt5:888",
            status=OrderStatus.FILLED,
        ),
        mode="mt5",
    )
    mt_pos = Position(
        id="888",
        symbol="XAUUSD",
        side=Side.BUY,
        lots=0.01,
        entry_price=4456.21,
        stop_loss=4440.0,
        take_profit=4480.0,
        unrealized_pnl=1.25,
    )
    result = sync_journal_with_mt5(journal, [mt_pos], mode="mt5")
    assert result["updated"] == 1
    row = journal.list(1)[0]
    assert row.ticket == "888"
    assert row.entry == 4456.21
    assert row.stop_loss == 4440.0
    assert row.take_profit == 4480.0
    assert row.unrealized_pnl == 1.25
    assert row.mode == "mt5"


def test_sync_journal_closes_row_when_mt5_position_gone():
    journal = TradeJournal()
    journal.record_mt5_open(
        Order(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            status=OrderStatus.FILLED,
            comment="mt5:999",
        ),
        Position(
            id="999",
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            entry_price=4450.0,
            unrealized_pnl=2.0,
        ),
        mode="mt5",
    )
    from app.models.domain import Tick, utcnow

    tick = Tick(symbol="XAUUSD", bid=4452.0, ask=4452.3, mid=4452.15, timestamp=utcnow())
    result = sync_journal_with_mt5(journal, [], tick=tick, mode="mt5")
    assert result["closed"] == 1
    row = journal.list(1)[0]
    assert row.status == TradeStatus.CLOSED
    assert row.exit == 4452.0
    assert row.realized_pnl != 0.0


def test_wait_mt_position_polls_bridge(tmp_path: Path):
    bridge = MT4FileBridge(tmp_path, symbol="GOLD#", desk_symbol="XAUUSD")
    bridge.positions_file.write_text(
        "ticket,symbol,side,lots,open_price,sl,tp,profit\n"
        "777,GOLD#,BUY,0.01,4590.00,4580.00,4610.00,0.50\n"
    )
    pos = wait_mt_position(bridge, "777", timeout=1.0)
    assert pos is not None
    assert pos.id == "777"
    assert pos.symbol == "XAUUSD"
    assert pos.entry_price == 4590.0


@pytest.mark.asyncio
async def test_mt_demo_fill_logs_real_ticket(tmp_path: Path):
    bridge_dir = tmp_path / "bridge"
    bridge_dir.mkdir()
    (bridge_dir / "jm_status.csv").write_text("ok,1000,1000,0,t\n")
    (bridge_dir / "jm_ticks.csv").write_text("GOLD#,4591.00,4591.30,t\n")

    settings = Settings(
        execution_mode="paper",
        mt5_bridge_dir=str(bridge_dir),
        mt_remote_bridge=True,
        mt5_demo_account_code="DDDC3D",
        mt_symbol="GOLD#",
    )
    reg = PaperAccountRegistry(settings, store_path=tmp_path / "accounts.json")
    acct = reg.create(deposit=1000.0, label="XM MT5 Demo", follow_auto=True)
    acct.code = "DDDC3D"

    from app.engine.trading_engine import TradingEngine

    engine = TradingEngine(settings)
    engine.accounts = reg
    engine.mt = MT4FileBridge(bridge_dir, symbol="GOLD#", desk_symbol="XAUUSD")

    def fake_ea():
        import time

        for _ in range(40):
            if engine.mt.command_file.exists():
                text = engine.mt.command_file.read_text()
                if "OPEN" in text:
                    cmd_id = text.strip().splitlines()[-1].split(",")[0]
                    engine.mt.ack_file.write_text(f"{cmd_id},OK,555\n")
                    engine.mt.positions_file.write_text(
                        "ticket,symbol,side,lots,open_price,sl,tp,profit\n"
                        "555,GOLD#,BUY,0.01,4591.10,4580.00,4610.00,0.00\n"
                    )
                    return
            time.sleep(0.05)

    import threading

    t = threading.Thread(target=fake_ea, daemon=True)
    t.start()
    order = await engine.manual_order(
        OrderRequest(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            stop_loss=4580.0,
            take_profit=4610.0,
            strategy="AI_ML/EMA_RSI_Scalp",
            comment="sync-test",
        ),
        account=acct,
    )
    t.join(timeout=3)
    assert order.status.value == "FILLED"
    row = acct.journal.list(1)[0]
    assert row.ticket == "555"
    assert row.entry == 4591.10
    assert row.mode == "mt5"
    assert row.strategy == "AI_ML/EMA_RSI_Scalp"
    assert row.comment == "mt5:555"
