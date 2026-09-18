from app.gold_v61_hours import hour_route_label, side_hour_mali


def test_h16_h17_block_both_sides():
    assert side_hour_mali("BUY", 16) == "V6.1 H16/H17 hard block"
    assert side_hour_mali("SELL", 17) == "V6.1 H16/H17 hard block"
    assert hour_route_label(16) == "BLOCK"


def test_buy_only_hour_23():
    assert side_hour_mali("BUY", 23) is None
    assert side_hour_mali("SELL", 23) is not None
    assert hour_route_label(23) == "BUY"


def test_sell_whitelist_hours():
    for h in (1, 2, 5, 8, 12, 20, 21):
        assert side_hour_mali("SELL", h) is None, h
        assert side_hour_mali("BUY", h) is not None, h
        assert hour_route_label(h) == "SELL"


def test_asia_europe_sell_only_even_if_not_whitelisted():
    # Hour 3 is Asia-ish but not on SELL strict whitelist → still blocked
    assert side_hour_mali("BUY", 3) is not None
    assert side_hour_mali("SELL", 3) is not None


def test_hour_11_not_tradable():
    assert side_hour_mali("BUY", 11) is not None
    assert side_hour_mali("SELL", 11) is not None
