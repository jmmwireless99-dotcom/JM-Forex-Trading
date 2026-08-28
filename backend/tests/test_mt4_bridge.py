import time
from pathlib import Path

from app.brokers.mt4_bridge import MT4FileBridge
from app.models.domain import OrderRequest, Side


def test_bridge_reads_status_and_ticks(tmp_path: Path):
    bridge = MT4FileBridge(tmp_path, symbol="XAUUSD")
    (tmp_path / "jm_status.csv").write_text("ok,10000.00,10050.00,1,2026.07.20 14:00:00\n")
    (tmp_path / "jm_ticks.csv").write_text("XAUUSD,2350.10,2350.40,2026.07.20 14:00:00\n")
    (tmp_path / "jm_positions.csv").write_text(
        "ticket,symbol,side,lots,open_price,sl,tp,profit\n"
        "123,XAUUSD,BUY,0.10,2350.00,2340.00,2370.00,12.50\n"
    )

    assert bridge.is_online(max_age_seconds=60) is True
    tick = bridge.read_tick()
    assert tick is not None
    assert tick.symbol == "XAUUSD"
    assert tick.bid == 2350.10

    snap = bridge.snapshot()
    assert snap.balance == 10000.0
    assert snap.equity == 10050.0

    positions = bridge.open_positions()
    assert len(positions) == 1
    assert positions[0].side == Side.BUY
    assert positions[0].lots == 0.1


def test_place_order_waits_for_ack(tmp_path: Path):
    bridge = MT4FileBridge(tmp_path, symbol="XAUUSD")

    def fake_ea():
        # poll for command then write ack
        for _ in range(40):
            if bridge.command_file.exists():
                text = bridge.command_file.read_text()
                if "OPEN" in text:
                    cmd_id = text.strip().splitlines()[-1].split(",")[0]
                    bridge.ack_file.write_text(f"{cmd_id},OK,555\n")
                    return
            time.sleep(0.05)

    import threading

    t = threading.Thread(target=fake_ea, daemon=True)
    t.start()

    order = bridge.place_order(
        OrderRequest(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.10,
            stop_loss=2340.0,
            take_profit=2370.0,
            comment="test",
        ),
        timeout=3.0,
    )
    t.join(timeout=3)
    assert order.status.value == "FILLED"
    assert "555" in (order.comment or "")


def test_unconfigured_bridge_dir():
    from app.brokers.mt4_bridge import resolve_bridge
    from app.core.config import Settings

    assert resolve_bridge(Settings(mt4_bridge_dir="")) is None


def test_gold_symbol_maps_desk_to_mt_and_back(tmp_path: Path):
    bridge = MT4FileBridge(tmp_path, symbol="GOLD#", desk_symbol="XAUUSD")
    (tmp_path / "jm_ticks.csv").write_text("GOLD#,4591.36,4591.66,2026-08-28 15:37:00\n")
    (tmp_path / "jm_positions.csv").write_text(
        "ticket,symbol,side,lots,open_price,sl,tp,profit\n"
        "1,GOLD#,BUY,0.01,4590.00,4580.00,4610.00,1.50\n"
    )

    tick = bridge.read_tick()
    assert tick is not None
    assert tick.symbol == "XAUUSD"
    assert tick.bid == 4591.36

    positions = bridge.open_positions()
    assert positions[0].symbol == "XAUUSD"

    def fake_ea():
        for _ in range(40):
            if bridge.command_file.exists():
                text = bridge.command_file.read_text()
                if "OPEN" in text and "GOLD#" in text:
                    cmd_id = text.strip().splitlines()[-1].split(",")[0]
                    bridge.ack_file.write_text(f"{cmd_id},OK,777\n")
                    return
            time.sleep(0.05)

    import threading

    t = threading.Thread(target=fake_ea, daemon=True)
    t.start()
    order = bridge.place_order(
        OrderRequest(
            symbol="XAUUSD",
            side=Side.BUY,
            lots=0.01,
            stop_loss=4580.0,
            take_profit=4610.0,
            comment="gold-map",
        ),
        timeout=3.0,
    )
    t.join(timeout=3)
    assert order.status.value == "FILLED"
    cmd = bridge.command_file.read_text()
    assert "GOLD#" in cmd
    assert "XAUUSD" not in cmd.split("OPEN")[1].split("\n")[0]
