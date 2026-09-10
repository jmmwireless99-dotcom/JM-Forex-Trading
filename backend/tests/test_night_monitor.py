"""Tests for PH night trade monitoring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.analytics.night_monitor import (
    build_night_report,
    is_ph_night,
    ph_night_window_start,
)


def test_is_ph_night():
    # PH 10PM = UTC 14:00
    assert is_ph_night(datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)) is True
    # PH 10AM = UTC 02:00
    assert is_ph_night(datetime(2026, 8, 27, 2, 0, tzinfo=timezone.utc)) is False
    # PH 3AM = UTC 19:00
    assert is_ph_night(datetime(2026, 8, 27, 19, 0, tzinfo=timezone.utc)) is True


def test_ph_night_window_start():
    now = datetime(2026, 8, 27, 15, 30, tzinfo=timezone.utc)
    start = ph_night_window_start(now)
    assert start == datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc)


def test_build_night_report_ml(tmp_path: Path):
    path = tmp_path / "hist.jsonl"
    rows = [
        {
            "event": "labeled",
            "label": 0,
            "realized_pnl": -2.5,
            "opened_at": "2026-08-27T13:30:00+00:00",
            "closed_at": "2026-08-27T14:00:00+00:00",
            "close_reason": "stop_loss",
            "context": {"session": "overlap", "side": "BUY", "strategy": "smc"},
        },
        {
            "event": "labeled",
            "label": 1,
            "realized_pnl": 3.0,
            "opened_at": "2026-08-27T02:00:00+00:00",
            "closed_at": "2026-08-27T03:00:00+00:00",
            "close_reason": "take_profit",
            "context": {"session": "asia", "side": "BUY", "strategy": "ema_rsi"},
        },
        {
            "event": "labeled",
            "label": 0,
            "realized_pnl": -1.0,
            "opened_at": "2026-08-27T18:30:00+00:00",
            "closed_at": "2026-08-27T19:00:00+00:00",
            "close_reason": "stop_loss",
            "context": {"session": "ny", "side": "SELL", "strategy": "vwap"},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    now = datetime(2026, 8, 27, 23, 0, tzinfo=timezone.utc)
    report = build_night_report(now=now, ml_history_path=path)
    data = report.as_dict()

    assert data["ml_history"]["night"]["n"] == 2
    assert data["ml_history"]["day"]["n"] == 1
    assert data["by_night_session"]["overlap"]["n"] == 1
    assert data["by_night_session"]["ny"]["n"] == 1


def test_dedupe_paper_trades():
    trades = [
        {
            "status": "CLOSED",
            "opened_at": "2026-08-27T13:30:00+00:00",
            "realized_pnl": -2.0,
            "symbol": "XAUUSD",
            "side": "BUY",
            "strategy": "AI_ML/SMC",
            "entry": 4580.0,
        },
        {
            "status": "CLOSED",
            "opened_at": "2026-08-27T13:30:00+00:00",
            "realized_pnl": -2.0,
            "symbol": "XAUUSD",
            "side": "BUY",
            "strategy": "AI_ML/SMC",
            "entry": 4580.0,
        },
    ]
    now = datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc)
    report = build_night_report(now=now, paper_trades=trades)
    assert report.paper_trades["night"]["n"] == 1
