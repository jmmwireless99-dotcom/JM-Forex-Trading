"""V6.1 hour / session gates from JM_GOLD_SMALL_CANDLE_FLOW_SCALPER.

Display + lab analyzer only. Matches the EA with all routers ON:
  InpUseStrictProfitHours, InpUseProfitHourRouter, InpUseV38Refinement,
  InpUseSafeSessionAB, InpBlockH16H17All, InpBlockH17BuyOnly.
"""

from __future__ import annotations

from typing import Literal

Side = Literal["BUY", "SELL"]

STRICT_SELL = frozenset({1, 2, 5, 8, 12, 16, 17, 20, 21})
STRICT_BUY = frozenset({23})
HARD_BLOCK_ALL = frozenset({16, 17})

# ProfitHourAllowed exclusions (V3.7 + V3.8)
BUY_HOUR_BLOCK = frozenset({5, 6, 10, 12, 13, 14, 15, 19, 20, 4, 11, 16, 18, 22})
SELL_HOUR_BLOCK = frozenset({3, 6, 9, 11, 15, 18, 19, 22, 23, 7, 10, 13, 14})

ASIA_END = 7
EUROPE_END = 15


def _dir(side: Side) -> int:
    return 1 if side == "BUY" else -1


def hard_block_h16_h17(hour: int) -> bool:
    return hour in HARD_BLOCK_ALL


def strict_profit_hour_allowed(side: Side, hour: int) -> bool:
    if side == "SELL":
        return hour in STRICT_SELL
    if side == "BUY":
        return hour in STRICT_BUY
    return False


def profit_hour_allowed(side: Side, hour: int) -> bool:
    if side == "BUY":
        return hour not in BUY_HOUR_BLOCK
    return hour not in SELL_HOUR_BLOCK


def safe_ab_allowed(side: Side, hour: int) -> bool:
    """Asia 00–07 and Europe 07–15: SELL only. US 15–24: both."""
    if hour < EUROPE_END:
        return side == "SELL"
    return True


def h17_buy_blocked(side: Side, hour: int) -> bool:
    return side == "BUY" and hour == 17


def side_hour_mali(side: Side, hour: int) -> str | None:
    """First hard hour reject, or None if the hour is tradable for this side."""
    if hard_block_h16_h17(hour):
        return "V6.1 H16/H17 hard block"
    if h17_buy_blocked(side, hour):
        return "V4.2 H17 BUY block"
    if not strict_profit_hour_allowed(side, hour):
        return "strict-hour (BUY only H23 · SELL whitelist)"
    if not profit_hour_allowed(side, hour):
        return "hour router reject"
    if not safe_ab_allowed(side, hour):
        return "SAFE-AB (Asia/Europe SELL only)"
    return None


def hour_route_label(hour: int) -> str:
    if hour in HARD_BLOCK_ALL:
        return "BLOCK"
    if hour in STRICT_BUY and side_hour_mali("BUY", hour) is None:
        return "BUY"
    sell_ok = side_hour_mali("SELL", hour) is None
    buy_ok = side_hour_mali("BUY", hour) is None
    if sell_ok and buy_ok:
        return "BOTH"
    if sell_ok:
        return "SELL"
    if buy_ok:
        return "BUY"
    return "BLOCK"
