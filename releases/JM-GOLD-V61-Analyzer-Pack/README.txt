JM GOLD V6.1 Analyzer Pack
==========================
Version: 6.10 · Tag: V6.1-FINAL-H16-H17-BLOCK

Ito ang BEST gold scalper mo + live OK/WAIT/MALI panel.
Hindi binago ang entry, TP, SL, lots, o hour routers.

UNZIP then INSTALL
------------------
1. MT5 → File → Open Data Folder
2. Copy Experts\JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V4_2.mq5
      → MQL5\Experts\
3. Copy Include\JM_V61_LiveAnalyzer.mqh
      → MQL5\Include\
4. MetaEditor → open the .mq5 → Compile (F7)
   Dapat 0 errors
5. Tanggalin ang ibang gold EA sa GOLD# chart (isang EA lang)
6. Drag JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V4_2 sa GOLD# chart
7. Inputs (winning backtest):
     InpLots              = 0.01
     InpShowPanel         = true
     InpAllowBuy          = true
     InpAllowSell         = true
     InpUseStrictProfitHours = true
     InpBlockH16H17All    = true
8. Algo Trading ON (green)
9. DEMO account only

PANEL (sa chart Comment)
------------------------
BUY  OK / WAIT / MALI + reason
SELL OK / WAIT / MALI + reason

MALI = huwag pumasok. Reasons galing sa V6.1 gates:
  H16/H17 hard block · BUY only H23 · hour router · SAFE-AB
  no M5 flow · M1 disagrees · no small candle · score < need · RSI · no breakout

BACKTEST (your report)
----------------------
  +830 on 10k · PF 1.20 · 1455 trades · DD 1.95%
  SELL 1348 (45.5%) · BUY 107 (45.8%)

HUWAG
-----
- Dalawang EA sa iisang GOLD# chart
- Optimize / palitan TP-SL sa unang 2 weeks
- Real account
