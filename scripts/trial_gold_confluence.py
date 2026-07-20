#!/usr/bin/env python3
"""Accelerated paper trial for gold_confluence strategy."""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(ROOT))

from app.brokers.paper import PaperBroker
from app.core.config import Settings
from app.models.domain import OrderRequest, Tick
from app.risk.manager import RiskManager
from app.strategies.gold_confluence import GoldConfluenceStrategy


@dataclass
class TrialStats:
    signals: int = 0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    rejected: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0


def make_tick(price: float, ts: datetime) -> Tick:
    spread = 0.35
    return Tick(
        symbol="XAUUSD",
        bid=round(price - spread / 2, 2),
        ask=round(price + spread / 2, 2),
        mid=round(price, 2),
        timestamp=ts,
    )


def record_close(stats: TrialStats, pos) -> None:
    stats.trades += 1
    if pos.realized_pnl >= 0:
        stats.wins += 1
        stats.gross_profit += pos.realized_pnl
    else:
        stats.losses += 1
        stats.gross_loss += abs(pos.realized_pnl)


def run_trial(steps: int = 5000, seed: int = 7) -> dict:
    random.seed(seed)
    settings = Settings(
        initial_balance=1000,
        max_risk_per_trade_pct=0.5,
        max_open_positions=1,
        max_daily_loss_pct=5.0,  # allow full trial to finish for stats
    )
    strategy = GoldConfluenceStrategy(
        session_filter=False,
        news_filter=False,
        min_adx=18.0,
        min_atr=0.15,
        pullback_atr=0.40,
        rsi_buy_low=35.0,
        rsi_buy_high=58.0,
        rsi_sell_low=42.0,
        rsi_sell_high=65.0,
    )
    broker = PaperBroker(initial_balance=1000)
    risk = RiskManager(settings)
    stats = TrialStats()

    ts = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)
    price = 2350.0
    phase = 0.0

    for i in range(steps):
        phase += 0.045
        drift = math.sin(phase) * 0.6 + math.sin(phase * 0.23) * 0.4
        shock = random.gauss(0, 0.5)
        if i % 160 == 0:
            shock += random.choice([-1, 1]) * random.uniform(2.0, 4.5)
        price = max(1800.0, price + drift + shock)
        ts += timedelta(seconds=15)
        if ts.hour >= 20:
            ts = ts + timedelta(days=1)
            ts = ts.replace(hour=13, minute=0, second=0)

        tick = make_tick(price, ts)
        closed = broker.update_tick(tick)
        for pos in closed:
            record_close(stats, pos)
            risk.record_realized_pnl(pos.realized_pnl)

        signal = strategy.on_tick(tick)
        if not signal:
            continue
        stats.signals += 1

        opens = broker.open_positions()
        if any(p.symbol == signal.symbol and p.side == signal.side for p in opens):
            continue
        for p in list(opens):
            if p.symbol == signal.symbol and p.side != signal.side:
                c = broker.close_position(p.id, reason="reverse")
                if c:
                    record_close(stats, c)
                    risk.record_realized_pnl(c.realized_pnl)

        req = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            lots=0.10,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy=signal.strategy,
            comment=(signal.reason or "")[:50],
        )
        decision = risk.evaluate(
            req,
            balance=broker.balance,
            open_positions=broker.open_positions(),
            tick=tick,
        )
        if not decision.approved:
            stats.rejected += 1
            continue
        req.lots = decision.adjusted_lots or req.lots
        broker.place_order(req)

    for p in broker.open_positions():
        c = broker.close_position(p.id, reason="trial_end")
        if c:
            record_close(stats, c)

    snap = broker.snapshot()
    win_rate = (stats.wins / stats.trades * 100) if stats.trades else 0.0
    avg_win = stats.gross_profit / stats.wins if stats.wins else 0.0
    avg_loss = stats.gross_loss / stats.losses if stats.losses else 0.0
    return {
        "strategy": "gold_confluence",
        "steps": steps,
        "signals": stats.signals,
        "trades": stats.trades,
        "wins": stats.wins,
        "losses": stats.losses,
        "rejected": stats.rejected,
        "win_rate_pct": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "start_balance": 1000.0,
        "end_balance": round(snap.balance, 2),
        "pnl": round(snap.balance - 1000.0, 2),
        "pnl_pct": round((snap.balance - 1000.0) / 10.0, 2),
        "profit_factor": round(stats.gross_profit / stats.gross_loss, 2)
        if stats.gross_loss
        else None,
    }


if __name__ == "__main__":
    result = run_trial()
    print("=== GOLD CONFLUENCE PAPER TRIAL ===")
    for k, v in result.items():
        print(f"{k}: {v}")
