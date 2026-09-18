JM GOLD SCALPER V6.77 EA
=======================

Ito ang EXPERT ADVISOR (nag-o-order), hindi indicator.
Kopya ng JM SCALPING V6.77 na pinaste mo: SL $15 @ 0.01, dynamic TP,
V640 hours, V641/V642/V643 blocks, score >= 3.

HINDI nito papalitan ang V6.1. I-detach muna ang ibang gold EA.

FILES (kopyahin LAHAT sa iisang folder)
--------------------------------------
  JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V6_77.mq5
  JM_GOLD_V656_CompleteAnalyzer.mqh
  JM_GOLD_V680_LossRootCauseAnalyzer.mqh

INSTALL
-------
1. MT5 → File → Open Data Folder
2. Buksan MQL5\Experts\
3. Copy ang TATLONG files diyan (magkasama — huwag hiwalayin)
4. MetaEditor → open JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V6_77.mq5 → F7
   Dapat 0 errors. Kung missing .mqh, "cannot open include" lalabas.
5. Tanggalin ang V6.1 / V6.20 / EMA200 EA sa GOLD# chart (isang EA lang)
6. Drag V6.77 sa GOLD# chart
7. Inputs (default winning pack):
     InpSymbol                    = GOLD#
     InpLots                      = 0.01
     InpMagic                     = 26091077
     InpBrokerUtcOffsetHours      = 3
     InpUseV640ProfitHourRouter   = true
     InpAllowBuy / InpAllowSell   = true
     InpFixedSLUsd                = 15.0
     InpUseDynamicTP              = true
8. Algo Trading ON (green)
9. DEMO / Strategy Tester lang muna. Every tick. M1 + M5 history kailangan.

PAANO MALALAMAN KUNG BUHAY
--------------------------
Experts tab: "JM GOLD V6.77 | V6.55 BASE | V6.77-BEST-MASTER-SL15"
Chart: lot label. Optional InpShowPanel = true para sa dashboard.

V640 HOURS (server GMT+3 = PHT UTC+8 minus 5)
---------------------------------------------
  SELL  server H04, H05, H08, H11, H12, H21
        PHT     09:00, 10:00, 13:00, 16:00, 17:00, 02:00
  BUY   server H05, H08, H17, H19, H22
        PHT     10:00, 13:00, 22:00, 00:00, 03:00

HUWAG
-----
- Dalawang gold EA sa iisang GOLD# chart
- Live / real account hangga't hindi tapos ang demo retest
- Palitan ang V6.1 file (V4_2.mq5) — hiwalay ito
- I-optimize agad ang TP/SL
- Ihiwalay ang .mqh files sa ibang folder
