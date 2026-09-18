from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EA = ROOT / "mt5" / "Experts" / "JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V6_77.mq5"
V61 = ROOT / "mt5" / "Experts" / "JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V4_2.mq5"
IND = ROOT / "mt5" / "Indicators" / "JM_GOLD_Session_Signal_v1.mq5"
V656 = ROOT / "mt5" / "Experts" / "JM_GOLD_V656_CompleteAnalyzer.mqh"
V680 = ROOT / "mt5" / "Experts" / "JM_GOLD_V680_LossRootCauseAnalyzer.mqh"


def test_v677_ea_is_trading_expert():
    mq5 = EA.read_text(encoding="utf-8")
    assert '#property version   "6.77"' in mq5
    assert "#include <Trade/Trade.mqh>" in mq5
    assert "trade.Buy" in mq5
    assert "trade.Sell" in mq5
    assert "InpMagic               = 26091077" in mq5
    assert "InpFixedSLUsd           = 15.0" in mq5
    assert "InpUseDynamicTP           = true" in mq5
    assert "InpUseV640ProfitHourRouter = true" in mq5
    assert "InpV641BlockSellADX20To25 = true" in mq5
    assert "InpV642BlockBuyGap050To100 = true" in mq5
    assert "InpV643BlockSellGap075To100 = true" in mq5
    assert "InpMinFlowScore       = 3" in mq5
    assert '#include "JM_GOLD_V656_CompleteAnalyzer.mqh"' in mq5
    assert '#include "JM_GOLD_V680_LossRootCauseAnalyzer.mqh"' in mq5
    assert "OnTester" in mq5
    assert "PrintCompleteAnalyzer" in mq5
    assert "PrintV680LossRootCause" in mq5
    assert "V640ProfitHourAllowed" in mq5
    assert "GOLD#" in mq5


def test_v677_v640_hours_in_ea():
    mq5 = EA.read_text(encoding="utf-8")
    assert "if(hour==4  && dir<0) return true;" in mq5
    assert "if(hour==5)           return true;" in mq5
    assert "if(hour==8)           return true;" in mq5
    assert "if(hour==11 && dir<0) return true;" in mq5
    assert "if(hour==12 && dir<0) return true;" in mq5
    assert "if(hour==17 && dir>0) return true;" in mq5
    assert "if(hour==19 && dir>0) return true;" in mq5
    assert "if(hour==21 && dir<0) return true;" in mq5
    assert "if(hour==22 && dir>0) return true;" in mq5


def test_v61_ea_untouched():
    mq5 = V61.read_text(encoding="utf-8")
    assert '#property version   "6.10"' in mq5
    assert "26091077" not in mq5


def test_session_indicator_still_visual_only():
    mq5 = IND.read_text(encoding="utf-8")
    assert "OrderSend" not in mq5
    assert "Trade.mqh" not in mq5


def test_analyzer_helpers_sit_next_to_ea():
    v656 = V656.read_text(encoding="utf-8")
    v680 = V680.read_text(encoding="utf-8")
    assert "void PrintCompleteAnalyzer()" in v656
    assert "int V656Collect" in v656
    assert "void PrintV680LossRootCause" in v680
    assert "g_symbol" in v656
    assert "InpMagic" in v656


def test_v677_pack_zip_has_ea_and_includes():
    import zipfile

    zpath = ROOT / "releases" / "JM-GOLD-V677-Pack.zip"
    assert zpath.is_file()
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
    assert "Experts/JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V6_77.mq5" in names
    assert "Experts/JM_GOLD_V656_CompleteAnalyzer.mqh" in names
    assert "Experts/JM_GOLD_V680_LossRootCauseAnalyzer.mqh" in names
    assert "SETUP.txt" in names
