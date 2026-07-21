"""London Judas Swing & Liquidity Sweep — Asian range trap → FVG limit entry."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import Candle, OrderType, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.london_session import (
    LONDON_PIP,
    calculate_asian_range,
    is_london_entry_window,
    is_london_sweep_window,
    pending_expire_at,
    price_from_pips,
)
from app.strategies.news_calendar import check_london_news_blackout


@dataclass
class FVG:
    high: float
    low: float
    mid: float
    bias: str  # BUY | SELL


def _swing_low_broken(bars: list[Candle], lookback: int = 8) -> bool:
    if len(bars) < lookback + 2:
        return False
    window = bars[-(lookback + 1) : -1]
    swing = min(c.low for c in window)
    return bars[-1].close < swing


def _swing_high_broken(bars: list[Candle], lookback: int = 8) -> bool:
    if len(bars) < lookback + 2:
        return False
    window = bars[-(lookback + 1) : -1]
    swing = max(c.high for c in window)
    return bars[-1].close > swing


def find_bearish_fvg(bars: list[Candle]) -> FVG | None:
    """Imbalance: candle1.low > candle3.high → gap mid = 50% equilibrium."""
    if len(bars) < 3:
        return None
    a, _, c = bars[-3], bars[-2], bars[-1]
    if a.low > c.high:
        hi, lo = a.low, c.high
        return FVG(high=hi, low=lo, mid=round((hi + lo) / 2, 2), bias="SELL")
    return None


def find_bullish_fvg(bars: list[Candle]) -> FVG | None:
    if len(bars) < 3:
        return None
    a, _, c = bars[-3], bars[-2], bars[-1]
    if a.high < c.low:
        hi, lo = c.low, a.high
        return FVG(high=hi, low=lo, mid=round((hi + lo) / 2, 2), bias="BUY")
    return None


class LondonJudasSweepStrategy(Strategy):
    """London 07–11 UTC Judas Swing: sweep Asia H/L → ChoCH → FVG 50% limit."""

    name = "London_Judas_Sweep"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 240,
        *,
        min_sweep_pips: float = 5.0,
        max_sweep_pips: float = 15.0,
        sl_buffer_pips: float = 12.0,
        max_spread_pips: float = 30.0,
        news_filter: bool = True,
        reward_r: float = 3.0,
    ) -> None:
        super().__init__(lookback=lookback)
        self.min_sweep_pips = min_sweep_pips
        self.max_sweep_pips = max_sweep_pips
        self.sl_buffer_pips = sl_buffer_pips
        self.max_spread_pips = max_spread_pips
        self.news_filter = news_filter
        self.reward_r = reward_r
        self.last_checklist: list[dict] = []
        self.last_block_reason: str | None = None
        self.last_range: dict | None = None
        self.last_zones: list[dict] = []
        self._structure_bars: list[Candle] = []
        self._m1_bars: list[Candle] = []
        self._fired_keys: set[str] = set()

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def set_m1_bars(self, candles: list[Candle]) -> None:
        self._m1_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        bars = self._structure_bars or candles
        self.last_checklist = []
        self.last_block_reason = None

        if not is_london_entry_window(tick.timestamp):
            self.last_block_reason = "Outside London entry window (07:00–11:00 UTC)"
            return None

        if self.news_filter:
            news = check_london_news_blackout(tick.timestamp, before_minutes=15)
            if news.blocked:
                self.last_block_reason = news.reason
                return None

        spread = abs(tick.ask - tick.bid)
        spread_pips = spread / LONDON_PIP
        if spread_pips > self.max_spread_pips:
            self.last_block_reason = (
                f"Spread too wide ({spread_pips:.0f} pips > {self.max_spread_pips:.0f})"
            )
            return None

        asian = calculate_asian_range(bars, as_of=tick.timestamp)
        if asian is None and self._m1_bars:
            asian = calculate_asian_range(self._m1_bars, as_of=tick.timestamp)
        if asian is None:
            self.last_block_reason = "Asian range not ready (need 00:00–06:00 UTC bars)"
            return None

        self.last_range = {
            "date": asian.session_date.isoformat(),
            "high": asian.high,
            "low": asian.low,
            "mid": asian.mid,
            "range_pips": asian.range_pips,
            "adx": None,
        }
        self.last_zones = [
            {
                "zone_type": "ASIAN_HIGH",
                "price_high": asian.high,
                "price_low": asian.high,
                "is_swept": False,
            },
            {
                "zone_type": "ASIAN_LOW",
                "price_high": asian.low,
                "price_low": asian.low,
                "is_swept": False,
            },
        ]

        cur = bars[-1]
        min_sweep = price_from_pips(self.min_sweep_pips)
        max_sweep = price_from_pips(self.max_sweep_pips)
        sl_buf = price_from_pips(self.sl_buffer_pips)

        # Prefer M5 ChoCH; fall back to M1 if provided
        choch_bars = bars
        if self._m1_bars and len(self._m1_bars) >= 20:
            choch_bars = self._m1_bars

        # --- Bearish Judas (SELL) ---
        sweep_high = cur.high - asian.high
        if (
            is_london_sweep_window(tick.timestamp) or is_london_entry_window(tick.timestamp)
        ) and min_sweep <= sweep_high <= max_sweep:
            rejected = cur.close <= asian.high
            choch = _swing_low_broken(choch_bars)
            fvg = find_bearish_fvg(bars)
            self.last_checklist = [
                {"name": "Asia High sweep", "ok": True, "detail": f"+{sweep_high / LONDON_PIP:.1f}p"},
                {"name": "Reject back inside", "ok": rejected, "detail": f"close={cur.close}"},
                {"name": "ChoCH lower-low", "ok": choch, "detail": "M5/M1"},
                {"name": "Bearish FVG", "ok": fvg is not None, "detail": str(fvg.mid if fvg else "—")},
            ]
            if rejected and choch and fvg and fvg.bias == "SELL":
                key = f"SELL-{asian.session_date}-{round(fvg.mid, 1)}"
                if key not in self._fired_keys:
                    self._fired_keys.add(key)
                    self.last_zones[0]["is_swept"] = True
                    sweep_px = cur.high
                    entry = fvg.mid
                    sl = round(sweep_px + sl_buf, 2)
                    risk = abs(sl - entry)
                    tp_asia = asian.low
                    tp_rrr = round(entry - self.reward_r * risk, 2)
                    # Prefer Asia low if it offers ≥ ~1R, else RRR target
                    tp = tp_asia if (entry - tp_asia) >= risk * 0.9 else tp_rrr
                    rr = round((entry - tp) / risk, 2) if risk else self.reward_r
                    return Signal(
                        strategy=self.name,
                        symbol=tick.symbol,
                        side=Side.SELL,
                        strength=0.92,
                        reason=(
                            f"London Judas SELL · AsiaH {asian.high} swept "
                            f"→ ChoCH → FVG50 {entry} · SL {sl} · TP {tp}"
                        ),
                        stop_loss=sl,
                        take_profit=tp,
                        order_type=OrderType.LIMIT,
                        limit_price=entry,
                        expire_at=pending_expire_at(tick.timestamp),
                        sweep_price=sweep_px,
                        timestamp=tick.timestamp,
                    )

        # --- Bullish Judas (BUY) ---
        sweep_low = asian.low - cur.low
        if (
            is_london_sweep_window(tick.timestamp) or is_london_entry_window(tick.timestamp)
        ) and min_sweep <= sweep_low <= max_sweep:
            rejected = cur.close >= asian.low
            choch = _swing_high_broken(choch_bars)
            fvg = find_bullish_fvg(bars)
            self.last_checklist = [
                {"name": "Asia Low sweep", "ok": True, "detail": f"+{sweep_low / LONDON_PIP:.1f}p"},
                {"name": "Reject back inside", "ok": rejected, "detail": f"close={cur.close}"},
                {"name": "ChoCH higher-high", "ok": choch, "detail": "M5/M1"},
                {"name": "Bullish FVG", "ok": fvg is not None, "detail": str(fvg.mid if fvg else "—")},
            ]
            if rejected and choch and fvg and fvg.bias == "BUY":
                key = f"BUY-{asian.session_date}-{round(fvg.mid, 1)}"
                if key not in self._fired_keys:
                    self._fired_keys.add(key)
                    self.last_zones[1]["is_swept"] = True
                    sweep_px = cur.low
                    entry = fvg.mid
                    sl = round(sweep_px - sl_buf, 2)
                    risk = abs(entry - sl)
                    tp_asia = asian.high
                    tp_rrr = round(entry + self.reward_r * risk, 2)
                    tp = tp_asia if (tp_asia - entry) >= risk * 0.9 else tp_rrr
                    return Signal(
                        strategy=self.name,
                        symbol=tick.symbol,
                        side=Side.BUY,
                        strength=0.92,
                        reason=(
                            f"London Judas BUY · AsiaL {asian.low} swept "
                            f"→ ChoCH → FVG50 {entry} · SL {sl} · TP {tp}"
                        ),
                        stop_loss=sl,
                        take_profit=tp,
                        order_type=OrderType.LIMIT,
                        limit_price=entry,
                        expire_at=pending_expire_at(tick.timestamp),
                        sweep_price=sweep_px,
                        timestamp=tick.timestamp,
                    )

        if not self.last_block_reason:
            self.last_block_reason = "No Judas sweep + ChoCH + FVG confluence yet"
        return None
