"""Smart Money Concepts scalp: liquidity sweep + MSS/ChoCH + FVG/OB retest (M5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import structure_levels, true_atr
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session


@dataclass
class Zone:
    kind: str  # ASIAN_HIGH / ASIAN_LOW / PDH / PDL / FVG / ORDER_BLOCK
    high: float
    low: float
    swept: bool = False
    side_bias: str | None = None  # BUY after low sweep, SELL after high sweep


def _swing_high(bars: list[Candle], i: int, left: int = 2, right: int = 2) -> bool:
    if i < left or i + right >= len(bars):
        return False
    h = bars[i].high
    return all(h > bars[i - j].high for j in range(1, left + 1)) and all(
        h >= bars[i + j].high for j in range(1, right + 1)
    )


def _swing_low(bars: list[Candle], i: int, left: int = 2, right: int = 2) -> bool:
    if i < left or i + right >= len(bars):
        return False
    lo = bars[i].low
    return all(lo < bars[i - j].low for j in range(1, left + 1)) and all(
        lo <= bars[i + j].low for j in range(1, right + 1)
    )


def _asia_window_bars(bars: list[Candle], now: datetime) -> list[Candle]:
    """Candles in today's Asia box (UTC 23:00 previous → 07:00, approx PH morning)."""
    utc = now.astimezone(timezone.utc)
    # Asia PH 7AM–3PM-ish liquidity often formed overnight UTC
    # Use UTC 00:00–07:00 of current UTC day as Asia range builder
    start = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=7)
    if utc.hour < 7:
        # Still inside Asia — use previous day's 00–07 as completed box if thin
        start = start - timedelta(days=1)
        end = start + timedelta(hours=7)
    out = [c for c in bars if start <= c.timestamp.astimezone(timezone.utc) < end]
    return out


def _prev_day_bars(bars: list[Candle], now: datetime) -> list[Candle]:
    utc = now.astimezone(timezone.utc)
    day0 = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_prev = day0 - timedelta(days=1)
    return [c for c in bars if day_prev <= c.timestamp.astimezone(timezone.utc) < day0]


def _find_fvg(bars: list[Candle]) -> Zone | None:
    """3-candle Fair Value Gap on most recent structure."""
    if len(bars) < 3:
        return None
    a, b, c = bars[-3], bars[-2], bars[-1]
    # Bullish FVG: candle1 high < candle3 low
    if a.high < c.low:
        return Zone("FVG", high=c.low, low=a.high, side_bias="BUY")
    # Bearish FVG: candle1 low > candle3 high
    if a.low > c.high:
        return Zone("FVG", high=a.low, low=c.high, side_bias="SELL")
    return None


def _find_order_block(bars: list[Candle], bias: str) -> Zone | None:
    """Last opposing candle before impulsive move."""
    if len(bars) < 6:
        return None
    window = bars[-8:-1]
    if bias == "BUY":
        # Last bearish candle before up move
        for c in reversed(window):
            if c.close < c.open:
                return Zone("ORDER_BLOCK", high=c.high, low=c.low, side_bias="BUY")
    else:
        for c in reversed(window):
            if c.close > c.open:
                return Zone("ORDER_BLOCK", high=c.high, low=c.low, side_bias="SELL")
    return None


class LiquiditySweepSmcStrategy(Strategy):
    name = "Liquidity_Sweep_SMC"
    candle_driven = True

    def __init__(
        self,
        lookback: int = 240,
        *,
        news_filter: bool | None = None,
        session_filter: bool | None = None,
        require_sweep: bool = True,
    ) -> None:
        super().__init__(lookback=lookback)
        settings = get_settings()
        self.news_filter = settings.news_filter if news_filter is None else news_filter
        self.session_filter = (
            settings.session_filter if session_filter is None else session_filter
        )
        self.require_sweep = require_sweep
        self.last_checklist: list[str] = []
        self.last_block_reason: str | None = None
        self.last_zones: list[dict] = []
        self._structure_bars: list[Candle] = []

    def set_structure_bars(self, candles: list[Candle]) -> None:
        self._structure_bars = list(candles)

    def evaluate(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        bars = self._structure_bars or candles
        self.last_checklist = []
        self.last_block_reason = None
        self.last_zones = []

        if len(bars) < 40:
            self.last_block_reason = "Need 40+ M5 bars for SMC"
            return None

        if self.news_filter:
            news = check_news_blackout(tick.timestamp)
            if news.blocked:
                self.last_block_reason = news.reason
                return None

        if self.session_filter:
            window = classify_session(tick.timestamp)
            if window.tier == SessionTier.AVOID:
                self.last_block_reason = window.reason
                return None

        atr = true_atr(bars, 14)
        if atr is None or atr <= 0:
            self.last_block_reason = "ATR warming up"
            return None

        now = tick.timestamp
        asia = _asia_window_bars(bars, now)
        prev_day = _prev_day_bars(bars, now)
        zones: list[Zone] = []
        if asia:
            zones.append(
                Zone("ASIAN_HIGH", high=max(c.high for c in asia), low=max(c.high for c in asia))
            )
            zones.append(
                Zone("ASIAN_LOW", high=min(c.low for c in asia), low=min(c.low for c in asia))
            )
        if prev_day:
            zones.append(
                Zone("PDH", high=max(c.high for c in prev_day), low=max(c.high for c in prev_day))
            )
            zones.append(
                Zone("PDL", high=min(c.low for c in prev_day), low=min(c.low for c in prev_day))
            )

        cur = bars[-1]
        pad = 0.1 * atr

        # Detect sweeps: wick beyond liquidity then close back inside
        swept_bias: str | None = None
        sweep_label = ""
        for z in zones:
            if z.kind in {"ASIAN_HIGH", "PDH"}:
                if cur.high > z.high + pad and cur.close < z.high:
                    z.swept = True
                    swept_bias = "SELL"
                    sweep_label = f"{z.kind} sweep"
            elif z.kind in {"ASIAN_LOW", "PDL"}:
                if cur.low < z.low - pad and cur.close > z.low:
                    z.swept = True
                    swept_bias = "BUY"
                    sweep_label = f"{z.kind} sweep"

        # Market structure shift / change of character around last swings
        mss_bias: str | None = None
        recent = bars[-20:]
        swing_highs = [recent[i].high for i in range(len(recent)) if _swing_high(recent, i)]
        swing_lows = [recent[i].low for i in range(len(recent)) if _swing_low(recent, i)]
        if swing_highs and cur.close > max(swing_highs[-2:] if len(swing_highs) >= 2 else swing_highs):
            mss_bias = "BUY"
        if swing_lows and cur.close < min(swing_lows[-2:] if len(swing_lows) >= 2 else swing_lows):
            mss_bias = "SELL"

        fvg = _find_fvg(bars)
        if fvg:
            zones.append(fvg)
        ob = _find_order_block(bars, swept_bias or mss_bias or "BUY")
        if ob:
            zones.append(ob)

        self.last_zones = [
            {
                "zone_type": z.kind,
                "price_high": round(z.high, 2),
                "price_low": round(z.low, 2),
                "is_swept": z.swept,
            }
            for z in zones
        ]

        bias = swept_bias or mss_bias
        if self.require_sweep and swept_bias is None:
            self.last_block_reason = "Waiting for Asia/PDH-PDL liquidity sweep"
            self.last_checklist = [
                f"zones={len(zones)} mss={mss_bias}",
                f"asia_bars={len(asia)} prev_day={len(prev_day)}",
            ]
            return None

        if bias is None:
            self.last_block_reason = "No MSS/ChoCH after sweep"
            return None

        # Entry: price retesting FVG or OB aligned with bias
        entry_zone = None
        for z in zones:
            if z.kind not in {"FVG", "ORDER_BLOCK"}:
                continue
            if z.side_bias and z.side_bias != bias:
                continue
            if z.low - pad <= cur.close <= z.high + pad:
                entry_zone = z
                break
            if bias == "BUY" and cur.low <= z.high and cur.close >= z.low:
                entry_zone = z
                break
            if bias == "SELL" and cur.high >= z.low and cur.close <= z.high:
                entry_zone = z
                break

        if entry_zone is None:
            # Soft entry: after sweep + MSS, allow confirmation candle in direction
            if bias == "BUY" and cur.close > cur.open and mss_bias == "BUY":
                entry_zone = Zone("ORDER_BLOCK", high=cur.high, low=cur.low, side_bias="BUY")
            elif bias == "SELL" and cur.close < cur.open and mss_bias == "SELL":
                entry_zone = Zone("ORDER_BLOCK", high=cur.high, low=cur.low, side_bias="SELL")
            else:
                self.last_block_reason = f"Sweep ok ({sweep_label}) — waiting FVG/OB retest"
                return None

        side = Side.BUY if bias == "BUY" else Side.SELL
        reason = (
            f"SMC {side.value} · {sweep_label or 'structure'} · "
            f"{'MSS' if mss_bias else 'ChoCH'} · {entry_zone.kind} retest"
        )
        self.last_checklist = [
            f"sweep={sweep_label or 'none'} mss={mss_bias}",
            f"entry={entry_zone.kind} {entry_zone.low:.2f}-{entry_zone.high:.2f}",
            f"ATR={atr:.2f}",
        ]

        levels = structure_levels(
            side,
            entry=tick.ask if side == Side.BUY else tick.bid,
            candles=bars,
            atr=atr,
            reward_r=1.8,
            min_stop_atr=1.1,
            min_tp_atr=2.0,
        )
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=side,
            strength=0.9,
            reason=reason,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            timestamp=tick.timestamp,
        )
