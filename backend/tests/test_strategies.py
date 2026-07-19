from app.models.domain import Side, Tick
from app.strategies.ema_crossover import EmaCrossoverStrategy
from app.strategies.rsi_mean_reversion import RsiMeanReversionStrategy


def _feed(strategy, symbol: str, prices: list[float]):
    signals = []
    for price in prices:
        tick = Tick(symbol=symbol, bid=price - 0.0001, ask=price + 0.0001, mid=price)
        sig = strategy.on_tick(tick)
        if sig:
            signals.append(sig)
    return signals


def test_ema_crossover_emits_buy_on_uptrend():
    strategy = EmaCrossoverStrategy(fast=3, slow=5)
    # Down then sharp up to force cross
    prices = [1.10 - i * 0.001 for i in range(8)] + [1.10 + i * 0.002 for i in range(10)]
    signals = _feed(strategy, "EURUSD", prices)
    assert any(s.side == Side.BUY for s in signals)


def test_rsi_emits_on_extremes():
    strategy = RsiMeanReversionStrategy(period=5, oversold=30, overbought=70)
    # Strong selloff
    down = [1.20 - i * 0.01 for i in range(20)]
    signals = _feed(strategy, "EURUSD", down)
    assert any(s.side == Side.BUY for s in signals)