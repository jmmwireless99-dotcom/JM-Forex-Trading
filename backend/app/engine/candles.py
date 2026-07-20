from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

from app.models.domain import Candle, Tick


def _bucket_start(ts: datetime, period: int) -> datetime:
    utc = ts.astimezone(timezone.utc)
    epoch = int(utc.timestamp())
    start = epoch - (epoch % period)
    return datetime.fromtimestamp(start, tz=timezone.utc)


class CandleAggregator:
    """Build OHLCV candles from ticks for live charting."""

    def __init__(self, period_seconds: int = 60, maxlen: int = 300) -> None:
        self.period_seconds = period_seconds
        self.maxlen = maxlen
        self._current: dict[str, Candle] = {}
        self._history: dict[str, deque[Candle]] = defaultdict(
            lambda: deque(maxlen=maxlen)
        )

    def update(self, tick: Tick) -> tuple[Candle | None, Candle]:
        """Return (closed_candle_or_None, current_forming_candle)."""
        bucket = _bucket_start(tick.timestamp, self.period_seconds)
        price = tick.mid
        current = self._current.get(tick.symbol)

        if current is None or current.open_time != bucket:
            closed = None
            if current is not None:
                current.is_closed = True
                current.timestamp = tick.timestamp
                self._history[tick.symbol].append(current)
                closed = current
            forming = Candle(
                symbol=tick.symbol,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1.0,
                period_seconds=self.period_seconds,
                open_time=bucket,
                timestamp=tick.timestamp,
                is_closed=False,
            )
            self._current[tick.symbol] = forming
            return closed, forming

        current.high = max(current.high, price)
        current.low = min(current.low, price)
        current.close = price
        current.volume += 1.0
        current.timestamp = tick.timestamp
        return None, current

    def history(self, symbol: str, limit: int = 200) -> list[Candle]:
        closed = list(self._history.get(symbol, []))[-limit:]
        current = self._current.get(symbol)
        if current is not None:
            return closed + [current]
        return closed

    def seed_history(self, symbol: str, candles: list[Candle]) -> None:
        self._history[symbol].clear()
        for candle in candles[-self.maxlen :]:
            self._history[symbol].append(candle)

    def closed_history(self, symbol: str, limit: int = 200) -> list[Candle]:
        return [c for c in list(self._history.get(symbol, [])) if c.is_closed][-limit:]
