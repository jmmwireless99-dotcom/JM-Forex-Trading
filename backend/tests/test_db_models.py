"""DB layer unit tests (no Postgres required)."""

from app.db.models import (
    DbTradeStatus,
    SignalSide,
    SignalStatus,
    ZoneType,
)
from app.db.seed import SEED_STRATEGIES
from app.db.session import db_enabled, ping_db


def test_seed_specs_match_prompt():
    names = {s["name"] for s in SEED_STRATEGIES}
    assert names == {
        "AI_ML",
        "EMA_RSI_Scalp",
        "EMA_VWAP_Scalp",
        "Liquidity_Sweep_SMC",
    }
    aiml = next(s for s in SEED_STRATEGIES if s["name"] == "AI_ML")
    assert aiml["parameters"]["session_children"]["asia"] == "EMA_RSI_Scalp"
    assert "london" not in aiml["parameters"]["session_children"]
    ema = next(s for s in SEED_STRATEGIES if s["name"] == "EMA_RSI_Scalp")
    assert ema["parameters"]["ema_trend"] == 200
    assert ema["parameters"]["rsi_buy_zone"] == [38, 52]
    smc = next(s for s in SEED_STRATEGIES if s["name"] == "Liquidity_Sweep_SMC")
    assert "FVG" in smc["parameters"]["entry_zones"]
    assert "SWEEP" in smc["parameters"]["entry_zones"]
    assert smc["parameters"]["sweep_valid_bars"] == 18
    assert "ASIAN_HIGH" in smc["parameters"]["liquidity"]


def test_enums_cover_gemini_spec():
    assert ZoneType.ASIAN_HIGH.value == "ASIAN_HIGH"
    assert ZoneType.FVG.value == "FVG"
    assert ZoneType.ORDER_BLOCK.value == "ORDER_BLOCK"
    assert SignalSide.BUY.value == "BUY"
    assert SignalStatus.PENDING.value == "PENDING"
    assert DbTradeStatus.CLOSED_TP.value == "CLOSED_TP"


def test_db_disabled_by_default():
    assert db_enabled() is False
    health = ping_db()
    assert health["configured"] is False
    assert health["ok"] is False
