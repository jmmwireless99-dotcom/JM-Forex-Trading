from app.brokers.market_data import MarketDataSimulator


def test_paper_sync_uses_live_provider():
    sim = MarketDataSimulator(["XAUUSD"], live_noise=0.0)
    sim.set_live_mid_provider(lambda _sym: 4118.5)
    updated = sim.pull_live_mids(force=True)
    assert updated["XAUUSD"] == 4118.5
    assert abs(sim.last_mids()["XAUUSD"] - 4118.5) < 0.01
    ticks = sim.next_ticks()
    assert abs(ticks[0].mid - 4118.5) < 0.5
