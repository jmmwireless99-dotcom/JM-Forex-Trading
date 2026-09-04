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

    saved_cmd: list[str] = []

    def fake_ea():
        for _ in range(40):
            if bridge.command_file.exists():
                text = bridge.command_file.read_text()
                if "OPEN" in text and "GOLD#" in text:
                    saved_cmd.append(text)
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
    assert saved_cmd
    cmd = saved_cmd[0]
    assert "GOLD#" in cmd
    assert "XAUUSD" not in cmd.split("OPEN")[1].split("\n")[0]


def test_remote_online_uses_any_heartbeat_file(tmp_path: Path):
    import os

    bridge = MT4FileBridge(tmp_path, symbol="GOLD#", desk_symbol="XAUUSD", remote_mode=True)
    status = tmp_path / "jm_status.csv"
    ticks = tmp_path / "jm_ticks.csv"
    status.write_text("ok,1000,1000,0,t\n")
    ticks.write_text("GOLD#,4591.00,4591.30,t\n")

    stale = time.time() - 20.0
    os.utime(status, (stale, stale))
    assert bridge.is_online() is True

    very_stale = time.time() - 60.0
    os.utime(status, (very_stale, very_stale))
    os.utime(ticks, (very_stale, very_stale))
    assert bridge.is_online() is False


def test_remote_defaults_longer_order_timeout(tmp_path: Path):
    bridge = MT4FileBridge(tmp_path, symbol="GOLD#", remote_mode=True)
    assert bridge.online_max_age == 45.0
    assert bridge.order_timeout == 30.0


def test_repair_legacy_xauusd_zero_tick(tmp_path: Path):
    from app.brokers.mt4_bridge import repair_mt_tick_csv

    fixed = repair_mt_tick_csv(
        "XAUUSD,0.00000,0.00000,2026.08.28 16:04:46\n",
        mt_symbol="GOLD#",
        live_mid=4592.0,
    )
    assert fixed.startswith("GOLD#,")
    bid, ask = fixed.split(",")[1:3]
    assert float(bid) > 4500
    assert float(ask) > float(bid)

    bridge = MT4FileBridge(tmp_path, symbol="GOLD#", desk_symbol="XAUUSD")
    (tmp_path / "jm_status.csv").write_text("ok,1000,1000,0,t\n")
    (tmp_path / "jm_ticks.csv").write_text(fixed)
    tick = bridge.read_tick()
    assert tick is not None
    assert tick.symbol == "XAUUSD"
    assert tick.bid > 4500
