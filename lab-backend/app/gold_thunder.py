"""JM Thunder GOLD Scalper V2.0.3 helpers (mirrors JM_THUNDER_GOLD_SCALPER.mq5)."""

from __future__ import annotations

MANUAL_PENDING_TYPES = frozenset(
    {
        "BUY_STOP",
        "SELL_STOP",
        "BUY_LIMIT",
        "SELL_LIMIT",
        "BUY_STOP_LIMIT",
        "SELL_STOP_LIMIT",
    }
)

DEF_TRAIL_START_USD = 0.50
DEF_TRAIL_DISTANCE_USD = 0.70
DEF_TRAIL_STEP_USD = 0.10
DEF_TRAIL_START_PTS = 50
DEF_TRAIL_DISTANCE_PTS = 70
DEF_TRAIL_STEP_PTS = 10
EA_MAGIC = 30250003
MANUAL_MAGIC = 0


def usd_to_points(
    usd: float,
    *,
    tick_size: float = 0.01,
    tick_value: float = 1.0,
    point: float = 0.01,
    ref_lot: float = 0.01,
) -> int:
    if usd <= 0 or tick_size <= 0 or tick_value <= 0 or point <= 0 or ref_lot <= 0:
        return 0
    return int(round(usd * tick_size / (tick_value * ref_lot) / point))


def trail_pts_from_usd(usd: float, fallback_pts: int, **kwargs) -> int:
    pts = usd_to_points(usd, **kwargs)
    if pts > 0:
        return pts
    pf = kwargs.get("point_factor", 1)
    return fallback_pts * pf


def default_trail_points() -> tuple[int, int, int]:
    start = trail_pts_from_usd(DEF_TRAIL_START_USD, DEF_TRAIL_START_PTS)
    dist = trail_pts_from_usd(DEF_TRAIL_DISTANCE_USD, DEF_TRAIL_DISTANCE_PTS)
    step = trail_pts_from_usd(DEF_TRAIL_STEP_USD, DEF_TRAIL_STEP_PTS)
    return start, dist, step


def in_session(gmt_hour: int, start: int = 8, end: int = 21, *, enabled: bool = True) -> bool:
    if not enabled:
        return True
    hour = gmt_hour % 24
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def is_manual_pending(
    magic: int,
    symbol: str,
    order_type: str,
    *,
    chart_symbol: str = "GOLD#",
    manage_manual: bool = True,
) -> bool:
    if not manage_manual:
        return False
    if symbol != chart_symbol:
        return False
    if magic != MANUAL_MAGIC:
        return False
    return order_type in MANUAL_PENDING_TYPES


def is_manual_position(
    magic: int,
    symbol: str,
    *,
    chart_symbol: str = "GOLD#",
    manage_manual: bool = True,
) -> bool:
    return manage_manual and magic == MANUAL_MAGIC and symbol == chart_symbol


def has_manual_exposure(
    positions: list[dict],
    orders: list[dict],
    *,
    chart_symbol: str = "GOLD#",
    manage_manual: bool = True,
) -> bool:
    for p in positions:
        if is_manual_position(
            int(p.get("magic", -1)),
            str(p.get("symbol", "")),
            chart_symbol=chart_symbol,
            manage_manual=manage_manual,
        ):
            return True
    for o in orders:
        if is_manual_pending(
            int(o.get("magic", -1)),
            str(o.get("symbol", "")),
            str(o.get("type", "")),
            chart_symbol=chart_symbol,
            manage_manual=manage_manual,
        ):
            return True
    return False


def pause_auto_when_manual(
    *,
    manage_manual: bool = True,
    pause: bool = False,
    has_manual: bool = False,
) -> bool:
    """Auto Thunder stays on. Manual trail is extra; never pause auto."""
    return False


def swing_unbroken(high: bool, values: list[float], strength: int = 5) -> float | None:
    """Newest bar is index 0 (MT5 shift 0). First unbroken swing high/low."""
    n = strength
    if len(values) <= n + 1:
        return None
    lookback = len(values) - 1
    for i in range(n + 1, lookback + 1):
        if i + n >= len(values):
            continue
        v = values[i]
        ok = True
        for k in range(1, n + 1):
            left = values[i - k]
            right = values[i + k]
            if high and (left >= v or right > v):
                ok = False
                break
            if not high and (left <= v or right < v):
                ok = False
                break
        if not ok:
            continue
        broken = False
        for j in range(i):
            if high and values[j] > v:
                broken = True
                break
            if not high and values[j] < v:
                broken = True
                break
        if broken:
            continue
        return v
    return None


def stop_entry(
    direction: int,
    swing: float,
    market: float,
    *,
    buffer: float = 0.50,
    min_gap: float = 0.20,
    max_dist: float = 50.0,
) -> float:
    if swing <= 0 or market <= 0:
        return 0.0
    if direction > 0:
        entry = swing + buffer
        gap = entry - market
    else:
        entry = swing - buffer
        gap = market - entry
    if gap < min_gap or gap > max_dist:
        return 0.0
    return entry


def apply_trail(
    buy: bool,
    bid: float,
    ask: float,
    open_price: float,
    cur_sl: float,
    *,
    trail_start_pts: int,
    trail_dist_pts: int,
    trail_step_pts: int,
    point: float = 0.01,
    stop_level: float = 0.0,
) -> float:
    profit_pts = (bid - open_price) / point if buy else (open_price - ask) / point
    if profit_pts < trail_start_pts:
        return cur_sl
    dist = max(trail_dist_pts * point, stop_level + point)
    if buy:
        cand = bid - dist
        if cand > bid - stop_level - point:
            return cur_sl
        if cur_sl > 0 and cand <= cur_sl:
            return cur_sl
        if cur_sl > 0 and cand < cur_sl + trail_step_pts * point:
            return cur_sl
        return cand
    cand = ask + dist
    if cand < ask + stop_level + point:
        return cur_sl
    if cur_sl > 0 and cand >= cur_sl:
        return cur_sl
    if cur_sl > 0 and cand > cur_sl - trail_step_pts * point:
        return cur_sl
    return cand
