from __future__ import annotations

from app.models.domain import Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.indicators import adx, atr, ema, rsi
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session, session_allows_entry

SIGNAL_COOLDOWN_SECONDS = 120


class GoldConfluenceStrategy(Strategy):
    """Recommended JM Forex XAUUSD desk strategy.

    Stack:
    1. Session — London / NY (prefer 13–16 UTC overlap)
    2. News — stand aside around NFP / CPI / FOMC-style USD prints
    3. Trend — EMA21 > EMA55 (or below for shorts)
    4. Strength — ADX >= threshold (skip chop)
    5. Pullback — RSI in value zone + price back near EMA21 after stretch
    6. Risk — ATR-based SL/TP
    """

    name = "gold_confluence"
    SYMBOL = "XAUUSD"

    def __init__(
        self,
        fast: int = 21,
        slow: int = 55,
        atr_period: int = 14,
        adx_period: int = 14,
        rsi_period: int = 14,
        min_adx: float = 24.0,
        rsi_buy_low: float = 40.0,
        rsi_buy_high: float = 55.0,
        rsi_sell_low: float = 45.0,
        rsi_sell_high: float = 60.0,
        pullback_atr: float = 0.55,
        sl_atr: float = 2.8,
        tp_atr: float = 4.2,
        min_atr: float = 0.55,
        session_filter: bool = False,
        prime_only: bool = False,
        news_filter: bool = True,
        news_before_minutes: int = 45,
        news_after_minutes: int = 30,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
    ) -> None:
        super().__init__(lookback=max(slow, adx_period * 2) + 50)
        self.fast = fast
        self.slow = slow
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.rsi_period = rsi_period
        self.min_adx = min_adx
        self.rsi_buy_low = rsi_buy_low
        self.rsi_buy_high = rsi_buy_high
        self.rsi_sell_low = rsi_sell_low
        self.rsi_sell_high = rsi_sell_high
        self.pullback_atr = pullback_atr
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr
        self.min_atr = min_atr
        self.session_filter = session_filter
        self.prime_only = prime_only
        self.news_filter = news_filter
        self.news_before_minutes = news_before_minutes
        self.news_after_minutes = news_after_minutes
        self.signal_cooldown_seconds = signal_cooldown_seconds
        self._armed: dict[str, Side | None] = {}
        self._last_signal_at: dict[str, float] = {}
        self.last_block_reason: str | None = None
        self.last_session_label: str | None = None

    def evaluate(self, tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None

        session = classify_session(tick.timestamp)
        self.last_session_label = session.label

        if self.session_filter and not session_allows_entry(
            tick.timestamp, prime_only=self.prime_only
        ):
            self.last_block_reason = session.reason
            return None

        if self.news_filter:
            news = check_news_blackout(
                tick.timestamp,
                before_minutes=self.news_before_minutes,
                after_minutes=self.news_after_minutes,
            )
            if news.blocked:
                self.last_block_reason = news.reason
                return None

        series = self.prices(tick.symbol)

        fast_ema = ema(series, self.fast)
        slow_ema = ema(series, self.slow)
        vol = atr(series, self.atr_period)
        strength = adx(series, self.adx_period)
        mom = rsi(series, self.rsi_period)
        if None in (fast_ema, slow_ema, vol, strength, mom):
            return None
        assert fast_ema is not None and slow_ema is not None
        assert vol is not None and strength is not None and mom is not None

        if vol < self.min_atr:
            self.last_block_reason = "ATR too low — choppy / quiet tape"
            return None
        if strength < self.min_adx:
            self.last_block_reason = f"ADX {strength:.1f} < {self.min_adx} — no trend"
            return None

        last_at = self._last_signal_at.get(tick.symbol, 0.0)
        if tick.timestamp.timestamp() - last_at < self.signal_cooldown_seconds:
            return None

        bullish = fast_ema > slow_ema
        bearish = fast_ema < slow_ema
        dist = tick.mid - fast_ema
        armed = self._armed.get(tick.symbol)

        if bullish and dist >= self.pullback_atr * vol:
            self._armed[tick.symbol] = Side.BUY
        elif bearish and dist <= -self.pullback_atr * vol:
            self._armed[tick.symbol] = Side.SELL
        elif not bullish and not bearish:
            self._armed[tick.symbol] = None

        # Confluence entry: armed pullback + RSI value zone + reclaim EMA
        if (
            armed == Side.BUY
            and bullish
            and abs(dist) <= self.pullback_atr * vol
            and self.rsi_buy_low <= mom <= self.rsi_buy_high
            and tick.mid >= fast_ema
        ):
            return self._build(tick, Side.BUY, vol, fast_ema, slow_ema, strength, mom, session.tier)

        if (
            armed == Side.SELL
            and bearish
            and abs(dist) <= self.pullback_atr * vol
            and self.rsi_sell_low <= mom <= self.rsi_sell_high
            and tick.mid <= fast_ema
        ):
            return self._build(tick, Side.SELL, vol, fast_ema, slow_ema, strength, mom, session.tier)

        self.last_block_reason = None
        return None

    def _build(
        self,
        tick: Tick,
        side: Side,
        vol: float,
        fast_ema: float,
        slow_ema: float,
        adx_val: float,
        rsi_val: float,
        tier: SessionTier,
    ) -> Signal:
        self._armed[tick.symbol] = None
        self._last_signal_at[tick.symbol] = tick.timestamp.timestamp()
        self.last_block_reason = None

        sl_dist = self.sl_atr * vol
        tp_dist = self.tp_atr * vol
        if side == Side.BUY:
            sl = tick.ask - sl_dist
            tp = tick.ask + tp_dist
        else:
            sl = tick.bid + sl_dist
            tp = tick.bid - tp_dist

        conf = min(1.0, (adx_val / 50.0) * (1.0 if tier == SessionTier.PRIME else 0.85))
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=round(conf, 3),
            reason=(
                f"Gold confluence {side.value} [{tier.value}]: "
                f"EMA{self.fast}/{self.slow} pullback · ADX={adx_val:.1f} · "
                f"RSI={rsi_val:.1f} · ATR={vol:.2f} · "
                f"SL={self.sl_atr}×ATR TP={self.tp_atr}×ATR"
            ),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
