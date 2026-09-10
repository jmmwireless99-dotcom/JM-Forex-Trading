"""Gold small-candle flow analyzer — OK / WEAK / MALI at entry.

Mirrors mt5/Experts/JM_Gold_Flow_Analyzer.mq5 so the lab desk and the EA
show the same checklist. Lab uses M5 only (M1 flow is proxied by M5 EMA 9/21).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from app.indicators import ema, rsi

Verdict = Literal["OK", "WEAK", "MALI", "WAIT"]
Side = Literal["BUY", "SELL"]

# Server/UTC hour bias for gold — SELL-heavy, matches the V6.2 short-only tests.
GOLD_SELL_HOURS = frozenset(range(0, 14))  # 00–13
GOLD_BUY_HOURS = frozenset({16, 17, 18, 19})
GOLD_WORST_HOURS = frozenset({21, 22, 23})


@dataclass
class Check:
    name: str
    verdict: Verdict
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "verdict": self.verdict, "detail": self.detail}


@dataclass
class SideScore:
    side: Side
    verdict: Verdict
    score: int
    required: int
    reasons: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "verdict": self.verdict,
            "score": self.score,
            "required": self.required,
            "reasons": self.reasons,
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class AnalyzerResult:
    symbol: str
    verdict: Verdict
    preferred_side: Side | None
    hour: int
    hour_bias: str
    adx: float | None
    rsi: float | None
    ema_fast: float | None
    ema_slow: float | None
    score: int
    required: int
    summary: str
    flow_proxy: str
    checks: list[Check]
    buy: SideScore
    sell: SideScore
    bar_time: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "verdict": self.verdict,
            "preferred_side": self.preferred_side,
            "hour": self.hour,
            "hour_bias": self.hour_bias,
            "adx": self.adx,
            "rsi": self.rsi,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "score": self.score,
            "required": self.required,
            "summary": self.summary,
            "flow_proxy": self.flow_proxy,
            "checks": [c.to_dict() for c in self.checks],
            "buy": self.buy.to_dict(),
            "sell": self.sell.to_dict(),
            "bar_time": self.bar_time,
        }


def true_atr(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev_c = float(candles[i - 1]["close"])
        trs.append(max(high - low, abs(high - prev_c), abs(low - prev_c)))
    window = trs[-period:]
    if len(window) < period:
        return None
    return sum(window) / period


def adx_last(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    """Wilder ADX on the last closed bar. None until warmup."""
    n = len(candles)
    if n < period * 2 + 2:
        return None
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr: list[float] = []
    for i in range(1, n):
        up = float(candles[i]["high"]) - float(candles[i - 1]["high"])
        down = float(candles[i - 1]["low"]) - float(candles[i]["low"])
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev_c = float(candles[i - 1]["close"])
        tr.append(max(high - low, abs(high - prev_c), abs(low - prev_c)))

    def _wilder(vals: list[float]) -> list[float]:
        seed = sum(vals[:period])
        out = [seed]
        for v in vals[period:]:
            seed = seed - seed / period + v
            out.append(seed)
        return out

    if len(tr) < period + 1:
        return None
    str_ = _wilder(tr)
    splus = _wilder(plus_dm)
    sminus = _wilder(minus_dm)
    dx: list[float] = []
    for s, p, m in zip(str_, splus, sminus):
        if s <= 1e-12:
            dx.append(0.0)
            continue
        pdi = 100.0 * p / s
        mdi = 100.0 * m / s
        denom = pdi + mdi
        dx.append(0.0 if denom <= 1e-12 else 100.0 * abs(pdi - mdi) / denom)
    if len(dx) < period:
        return None
    adx_seed = sum(dx[:period]) / period
    adx = adx_seed
    for v in dx[period:]:
        adx = (adx * (period - 1) + v) / period
    return round(adx, 2)


def hour_bias(hour: int, *, symbol: str) -> str:
    if symbol.upper() != "XAUUSD":
        return "NEUTRAL"
    h = hour % 24
    if h in GOLD_WORST_HOURS:
        return "WORST"
    if h in GOLD_BUY_HOURS:
        return "BUY"
    if h in GOLD_SELL_HOURS:
        return "SELL"
    return "NEUTRAL"


def required_score(
    side: Side,
    bias: str,
    *,
    base: int = 3,
    easier: int = -1,
    weak_add: int = 1,
    worst_add: int = 2,
) -> int:
    need = base
    if bias == "WORST":
        need += worst_add
    elif bias == "NEUTRAL":
        need += weak_add
    elif bias == side:
        need += easier
    else:
        need += worst_add  # against the hour
    return max(1, min(6, need))


def _small_candle(
    bar: dict[str, Any],
    atr: float,
    *,
    body_max: float = 0.45,
    range_atr: float = 0.7,
) -> tuple[bool, str]:
    high = float(bar["high"])
    low = float(bar["low"])
    body = abs(float(bar["close"]) - float(bar["open"]))
    span = high - low
    if span <= 1e-12:
        return False, "doji/flat — no range"
    body_ratio = body / span
    atr_ratio = span / atr if atr > 0 else 99.0
    ok = body_ratio <= body_max and atr_ratio <= range_atr
    detail = f"body {body_ratio:.2f} (≤{body_max}) · range {atr_ratio:.2f}×ATR (≤{range_atr})"
    return ok, detail


def _score_side(
    side: Side,
    *,
    bias: str,
    uptrend: bool,
    downtrend: bool,
    flow_buy: bool,
    flow_sell: bool,
    adx_v: float | None,
    adx_min: float,
    weak_adx: float,
    chop: bool,
    use_chop: bool,
    small: bool,
    small_detail: str,
    breakout_buy: bool,
    breakout_sell: bool,
    rsi_v: float | None,
    require_flow: bool,
    base_score: int,
    use_flow_score: bool,
) -> SideScore:
    checks: list[Check] = []
    reasons: list[str] = []
    score = 0
    aligned_trend = (side == "BUY" and uptrend) or (side == "SELL" and downtrend)
    aligned_flow = (side == "BUY" and flow_buy) or (side == "SELL" and flow_sell)
    broke = (side == "BUY" and breakout_buy) or (side == "SELL" and breakout_sell)

    if aligned_trend:
        score += 1
        checks.append(Check("M5 trend", "OK", "aligned"))
    else:
        reasons.append("counter-trend")
        checks.append(Check("M5 trend", "MALI", "against EMA20/50"))

    if adx_v is None:
        checks.append(Check("ADX", "WAIT", "warming up"))
        reasons.append("ADX warmup")
    elif adx_v >= adx_min:
        score += 1
        checks.append(Check("ADX", "OK", f"{adx_v:.1f} ≥ {adx_min:.0f}"))
    else:
        checks.append(Check("ADX", "WEAK", f"{adx_v:.1f} < {adx_min:.0f} chop"))
        if use_chop and chop and adx_v < weak_adx:
            reasons.append("chop + weak ADX")
            checks[-1] = Check("ADX", "MALI", f"{adx_v:.1f} chop+weak")

    if aligned_flow:
        score += 1
        checks.append(Check("M1/M5 flow", "OK", "aligned"))
    else:
        checks.append(Check("M1/M5 flow", "MALI" if require_flow else "WEAK", "against fast/slow EMA"))
        if require_flow:
            reasons.append("flow against")

    if small:
        score += 1
        checks.append(Check("Small candle", "OK", small_detail))
    else:
        reasons.append("not a small candle")
        checks.append(Check("Small candle", "MALI", small_detail))

    if broke:
        score += 1
        checks.append(Check("Breakout", "OK", f"{side} broke small-candle range"))
    else:
        reasons.append("no breakout")
        checks.append(Check("Breakout", "MALI", "no close beyond small candle"))

    if rsi_v is not None:
        rsi_ok = (side == "BUY" and rsi_v <= 62) or (side == "SELL" and rsi_v >= 38)
        if rsi_ok:
            score += 1
            checks.append(Check("RSI", "OK", f"{rsi_v:.1f}"))
        else:
            checks.append(Check("RSI", "WEAK", f"{rsi_v:.1f} stretched"))
            reasons.append("RSI stretched")
    else:
        checks.append(Check("RSI", "WAIT", "warming up"))

    need = required_score(side, bias, base=base_score)
    hard_mali = any(
        r in reasons
        for r in ("counter-trend", "flow against", "chop + weak ADX", "not a small candle", "no breakout")
    )
    if not use_flow_score:
        need = 1

    if hard_mali:
        need = max(need, score + 1)
        verdict: Verdict = "MALI"
    elif score < need:
        verdict = "MALI"
    elif score == need:
        verdict = "WEAK"
    else:
        verdict = "OK"

    if bias == "WORST":
        reasons.append("worst hour")
        if verdict == "OK":
            verdict = "WEAK"

    return SideScore(
        side=side,
        verdict=verdict,
        score=score,
        required=need,
        reasons=reasons,
        checks=checks,
    )


def analyze_entry(
    candles: list[dict[str, Any]],
    *,
    symbol: str,
    hour: int | None = None,
    m1_candles: list[dict[str, Any]] | None = None,
    ema_fast: int = 20,
    ema_slow: int = 50,
    flow_fast: int = 9,
    flow_slow: int = 21,
    adx_period: int = 14,
    adx_min: float = 16.0,
    weak_adx: float = 20.0,
    rsi_period: int = 14,
    atr_period: int = 14,
    body_max: float = 0.45,
    range_atr: float = 0.7,
    breakout_atr: float = 0.05,
    chop_gap_pct: float = 0.06,
    require_flow: bool = True,
    use_chop: bool = True,
    use_flow_score: bool = True,
    base_score: int = 3,
) -> AnalyzerResult:
    sym = symbol.upper()
    closed = candles[:-1] if len(candles) > 1 else candles
    bar_time = int(closed[-1]["time"]) if closed else 0

    if hour is None:
        if bar_time:
            hour = datetime.fromtimestamp(bar_time, tz=timezone.utc).hour
        else:
            hour = datetime.now(timezone.utc).hour
    bias = hour_bias(hour, symbol=sym)

    wait_buy = SideScore("BUY", "WAIT", 0, base_score, ["need more bars"], [])
    wait_sell = SideScore("SELL", "WAIT", 0, base_score, ["need more bars"], [])
    wait_checks = [Check("Bars", "WAIT", f"Need {ema_slow + 5}+ M5 bars (have {len(closed)})")]

    if len(closed) < ema_slow + 5:
        return AnalyzerResult(
            symbol=sym,
            verdict="WAIT",
            preferred_side=None,
            hour=hour,
            hour_bias=bias,
            adx=None,
            rsi=None,
            ema_fast=None,
            ema_slow=None,
            score=0,
            required=base_score,
            summary=f"WAIT — need {ema_slow + 5}+ M5 bars (have {len(closed)})",
            flow_proxy="m1" if m1_candles else "m5-ema9/21",
            checks=wait_checks,
            buy=wait_buy,
            sell=wait_sell,
            bar_time=bar_time,
        )

    closes = [float(c["close"]) for c in closed]
    e_fast = ema(closes, ema_fast)
    e_slow = ema(closes, ema_slow)
    flow_src = m1_candles[:-1] if m1_candles and len(m1_candles) > 1 else closed
    flow_closes = [float(c["close"]) for c in flow_src]
    f_fast = ema(flow_closes, flow_fast)
    f_slow = ema(flow_closes, flow_slow)
    rs = rsi(closes, rsi_period)
    atr = true_atr(closed, atr_period)
    adx_v = adx_last(closed, adx_period)

    ef, es = e_fast[-1], e_slow[-1]
    ff, fs = f_fast[-1], f_slow[-1]
    rv = rs[-1]
    if ef is None or es is None or atr is None or atr <= 0:
        return AnalyzerResult(
            symbol=sym,
            verdict="WAIT",
            preferred_side=None,
            hour=hour,
            hour_bias=bias,
            adx=adx_v,
            rsi=rv,
            ema_fast=ef,
            ema_slow=es,
            score=0,
            required=base_score,
            summary="WAIT — indicators warming up",
            flow_proxy="m1" if m1_candles else "m5-ema9/21",
            checks=[Check("Indicators", "WAIT", "EMA/ATR warmup")],
            buy=wait_buy,
            sell=wait_sell,
            bar_time=bar_time,
        )

    uptrend = ef > es
    downtrend = ef < es
    flow_buy = ff is not None and fs is not None and ff > fs
    flow_sell = ff is not None and fs is not None and ff < fs
    gap_pct = abs(ef - es) / float(closed[-1]["close"]) * 100.0
    chop = gap_pct < chop_gap_pct

    prev = closed[-2] if len(closed) >= 2 else closed[-1]
    cur = closed[-1]
    small, small_detail = _small_candle(prev, atr, body_max=body_max, range_atr=range_atr)
    buf = breakout_atr * atr
    breakout_buy = small and float(cur["close"]) > float(prev["high"]) + buf
    breakout_sell = small and float(cur["close"]) < float(prev["low"]) - buf

    buy = _score_side(
        "BUY",
        bias=bias,
        uptrend=uptrend,
        downtrend=downtrend,
        flow_buy=flow_buy,
        flow_sell=flow_sell,
        adx_v=adx_v,
        adx_min=adx_min,
        weak_adx=weak_adx,
        chop=chop,
        use_chop=use_chop,
        small=small,
        small_detail=small_detail,
        breakout_buy=breakout_buy,
        breakout_sell=breakout_sell,
        rsi_v=rv,
        require_flow=require_flow,
        base_score=base_score,
        use_flow_score=use_flow_score,
    )
    sell = _score_side(
        "SELL",
        bias=bias,
        uptrend=uptrend,
        downtrend=downtrend,
        flow_buy=flow_buy,
        flow_sell=flow_sell,
        adx_v=adx_v,
        adx_min=adx_min,
        weak_adx=weak_adx,
        chop=chop,
        use_chop=use_chop,
        small=small,
        small_detail=small_detail,
        breakout_buy=breakout_buy,
        breakout_sell=breakout_sell,
        rsi_v=rv,
        require_flow=require_flow,
        base_score=base_score,
        use_flow_score=use_flow_score,
    )

    market = [
        Check(
            "Hour",
            "MALI" if bias == "WORST" else "OK" if bias != "NEUTRAL" else "WEAK",
            f"{hour:02d}:00 UTC · {bias}",
        ),
        Check("M5 EMA", "OK", f"{ef:.2f} / {es:.2f} · {'up' if uptrend else 'down' if downtrend else 'flat'}"),
        Check("Chop gap", "MALI" if chop and use_chop else "OK", f"{gap_pct:.3f}% (toxic < {chop_gap_pct}%)"),
    ]

    ranked = sorted(
        (buy, sell),
        key=lambda s: ({"OK": 3, "WEAK": 2, "MALI": 1, "WAIT": 0}[s.verdict], s.score),
        reverse=True,
    )
    best = ranked[0]
    trade_side: Side | None = best.side if best.verdict in {"OK", "WEAK"} else None
    overall: Verdict
    if trade_side is not None:
        overall = best.verdict
    elif buy.verdict == "WAIT" and sell.verdict == "WAIT":
        overall = "WAIT"
    else:
        overall = "MALI"

    summary = _summary(best, trade_side, bias, hour)
    return AnalyzerResult(
        symbol=sym,
        verdict=overall,
        preferred_side=trade_side,
        hour=hour,
        hour_bias=bias,
        adx=adx_v,
        rsi=round(rv, 1) if rv is not None else None,
        ema_fast=round(ef, 2),
        ema_slow=round(es, 2),
        score=best.score,
        required=best.required,
        summary=summary,
        flow_proxy="m1" if m1_candles else "m5-ema9/21",
        checks=market,
        buy=buy,
        sell=sell,
        bar_time=bar_time,
    )


def _summary(best: SideScore, preferred: Side | None, bias: str, hour: int) -> str:
    if best.verdict == "OK" and preferred:
        return f"OK — {preferred} entry (score {best.score}/{best.required})"
    if best.verdict == "WEAK" and preferred:
        return f"WEAK — {preferred} caution (score {best.score}/{best.required})"
    why = ", ".join(best.reasons[:3]) or "no setup"
    side = preferred or best.side
    return f"MALI — huwag i-{side} ({why}) · hour {hour:02d} {bias}"


def verdict_for_side(result: AnalyzerResult, side: str) -> SideScore:
    return result.buy if side.upper() == "BUY" else result.sell
