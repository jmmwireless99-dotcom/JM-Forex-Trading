"""Capital-scaled lot sizing for JM FX desk entries."""

from __future__ import annotations


def lots_for_capital(
    capital_usd: float,
    *,
    lots_per_1000: float = 0.03,
    min_lots: float = 0.01,
) -> float:
    """0.03 lots per $1,000 capital (configurable via JM_LOTS_PER_1000_USD)."""
    if capital_usd <= 0:
        return min_lots
    lots = (capital_usd / 1000.0) * lots_per_1000
    return max(min_lots, round(lots, 2))
