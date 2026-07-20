from __future__ import annotations

from app.models.domain import Candle, Side, Signal, Tick
from app.strategies.base import Strategy
from app.strategies.entry_setup import (
    bearish_confirm,
    bullish_confirm,
    pulled_into_zone,
    recent_stretch_above,
    recent_stretch_below,
    structure_levels,
    true_atr,
)
from app.strategies.indicators import adx, ema, rsi
from app.strategies.news_calendar import check_news_blackout
from app.strategies.session import SessionTier, classify_session, session_allows_entry

# One setup per 3× M5 bars by default
SIGNAL_COOLDOWN_SECONDS = 900


class GoldConfluenceStrategy(Strategy):
    """XAUUSD confluence — decisions only on closed signal candles (default M5).

    Entry checklist (ALL must pass):
      1. London / NY session (not Asia)
      2. No high-impact USD news blackout
      3. EMA21 vs EMA55 trend aligned
      4. ADX shows real trend (not chop)
      5. ATR large enough (tradeable volatility)
      6. Prior stretch away from EMA21 (impulse existed)
      7. Pullback into EMA21 value zone
      8. Confirmation candle closes with trend (body strength)
      9. RSI in pullback value zone (not late chase)
     10. Structure SL beyond swing + ATR pad; TP ≥ 1.8R
    """

    name = "gold_confluence"
    SYMBOL = "XAUUSD"
    candle_driven = True

    def __init__(
        self,
        fast: int = 21,
        slow: int = 55,
        atr_period: int = 14,
        adx_period: int = 14,
        rsi_period: int = 14,
        min_adx: float = 25.0,
        rsi_buy_low: float = 38.0,
        rsi_buy_high: float = 55.0,
        rsi_sell_low: float = 45.0,
        rsi_sell_high: float = 62.0,
        pullback_atr: float = 0.65,
        min_atr: float = 0.90,
        session_filter: bool = False,
        prime_only: bool = False,
        news_filter: bool = True,
        news_before_minutes: int = 45,
        news_after_minutes: int = 30,
        signal_cooldown_seconds: int = SIGNAL_COOLDOWN_SECONDS,
        reward_r: float = 1.8,
    ) -> None:
        super().__init__(lookback=max(slow, adx_period * 2) + 80)
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
        self.min_atr = min_atr
        self.session_filter = session_filter
        self.prime_only = prime_only
        self.news_filter = news_filter
        self.news_before_minutes = news_before_minutes
        self.news_after_minutes = news_after_minutes
        self.signal_cooldown_seconds = signal_cooldown_seconds
        self.reward_r = reward_r
        self._last_signal_at: dict[str, float] = {}
        self.last_block_reason: str | None = None
        self.last_session_label: str | None = None
        self.last_checklist: list[dict] = []

    def evaluate(self, tick: Tick) -> Signal | None:
        # Tick path disabled — engine must call on_bar() on closed M5.
        return None

    def on_bar(self, candles: list[Candle], tick: Tick) -> Signal | None:
        if tick.symbol.upper() != self.SYMBOL:
            return None
        if len(candles) < self.slow + 5:
            self.last_block_reason = f"Waiting for {self.slow + 5} M5 bars"
            self.last_checklist = []
            return None

        session = classify_session(tick.timestamp)
        self.last_session_label = session.label
        checks: list[dict] = []

        def gate(name: str, ok: bool, detail: str) -> bool:
            checks.append({"name": name, "ok": ok, "detail": detail})
            return ok

        ok_session = True
        if self.session_filter:
            ok_session = session_allows_entry(
                tick.timestamp, prime_only=self.prime_only
            )
        else:
            # Auto/managed mode still requires London/NY quality hours.
            ok_session = session.tier.value in {"prime", "allowed"}
        if not gate("session", ok_session, session.reason):
            self.last_block_reason = session.reason
            self.last_checklist = checks
            return None

        news_ok = True
        news_detail = "No high-impact USD news blackout"
        if self.news_filter:
            news = check_news_blackout(
                tick.timestamp,
                before_minutes=self.news_before_minutes,
                after_minutes=self.news_after_minutes,
            )
            news_ok = not news.blocked
            news_detail = news.reason
        if not gate("news", news_ok, news_detail):
            self.last_block_reason = news_detail
            self.last_checklist = checks
            return None

        closes = [c.close for c in candles]
        fast_ema = ema(closes, self.fast)
        slow_ema = ema(closes, self.slow)
        vol = true_atr(candles, self.atr_period)
        strength = adx(closes, self.adx_period)
        mom = rsi(closes, self.rsi_period)
        if None in (fast_ema, slow_ema, vol, strength, mom):
            self.last_block_reason = "Indicators warming up"
            self.last_checklist = checks
            return None
        assert fast_ema is not None and slow_ema is not None
        assert vol is not None and strength is not None and mom is not None

        if not gate("atr", vol >= self.min_atr, f"ATR={vol:.2f} (min {self.min_atr})"):
            self.last_block_reason = "ATR too low — skip thin/chop tape"
            self.last_checklist = checks
            return None
        if not gate("adx", strength >= self.min_adx, f"ADX={strength:.1f} (min {self.min_adx})"):
            self.last_block_reason = f"ADX {strength:.1f} — no clear trend"
            self.last_checklist = checks
            return None

        last_at = self._last_signal_at.get(tick.symbol, 0.0)
        cool_ok = tick.timestamp.timestamp() - last_at >= self.signal_cooldown_seconds
        if not gate(
            "cooldown",
            cool_ok,
            f"{self.signal_cooldown_seconds}s between setups",
        ):
            self.last_block_reason = "Cooldown — waiting for next M5 setup window"
            self.last_checklist = checks
            return None

        bar = candles[-1]
        band = self.pullback_atr * vol
        bullish = fast_ema > slow_ema
        bearish = fast_ema < slow_ema

        stretch_buy = recent_stretch_above(candles, fast_ema + 0.45 * vol)
        stretch_sell = recent_stretch_below(candles, fast_ema - 0.45 * vol)
        pull_buy = pulled_into_zone(candles, mid=fast_ema, band=band)
        pull_sell = pull_buy
        rsi_buy = self.rsi_buy_low <= mom <= self.rsi_buy_high
        rsi_sell = self.rsi_sell_low <= mom <= self.rsi_sell_high
        conf_buy = bullish_confirm(bar) and bar.close >= fast_ema
        conf_sell = bearish_confirm(bar) and bar.close <= fast_ema

        buy_ready = (
            bullish
            and stretch_buy
            and pull_buy
            and rsi_buy
            and conf_buy
        )
        sell_ready = (
            bearish
            and stretch_sell
            and pull_sell
            and rsi_sell
            and conf_sell
        )

        gate("trend", bullish or bearish, f"EMA{self.fast}/{self.slow} {'UP' if bullish else 'DOWN' if bearish else 'FLAT'}")
        if bullish:
            gate("stretch", stretch_buy, "Prior push above EMA21")
            gate("pullback", pull_buy, "Price returned to EMA21 zone")
            gate("rsi_zone", rsi_buy, f"RSI={mom:.1f} in {self.rsi_buy_low}-{self.rsi_buy_high}")
            gate("confirm", conf_buy, "Bullish M5 close back above EMA21")
        elif bearish:
            gate("stretch", stretch_sell, "Prior push below EMA21")
            gate("pullback", pull_sell, "Price returned to EMA21 zone")
            gate("rsi_zone", rsi_sell, f"RSI={mom:.1f} in {self.rsi_sell_low}-{self.rsi_sell_high}")
            gate("confirm", conf_sell, "Bearish M5 close back below EMA21")
        else:
            self.last_block_reason = "No EMA trend"
            self.last_checklist = checks
            return None

        self.last_checklist = checks
        if not (buy_ready or sell_ready):
            failed = [c["name"] for c in checks if not c["ok"]]
            self.last_block_reason = "Setup incomplete: " + ", ".join(failed) if failed else "No confirm bar"
            return None

        side = Side.BUY if buy_ready else Side.SELL
        entry = tick.ask if side == Side.BUY else tick.bid
        levels = structure_levels(
            side,
            entry=entry,
            candles=candles,
            atr=vol,
            reward_r=self.reward_r,
        )
        self._last_signal_at[tick.symbol] = tick.timestamp.timestamp()
        self.last_block_reason = None

        tf = f"M{max(1, candles[-1].period_seconds // 60)}"
        return Signal(
            strategy=self.name,
            symbol=self.SYMBOL,
            side=side,
            strength=round(min(1.0, strength / 50.0), 3),
            reason=(
                f"{tf} confluence {side.value} [{session.tier.value}]: "
                f"trend+pullback+confirm · ADX={strength:.1f} RSI={mom:.1f} "
                f"ATR={vol:.2f} · SL swing/ATR risk={levels.risk} "
                f"TP={levels.reward_r}R"
            ),
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
        )
