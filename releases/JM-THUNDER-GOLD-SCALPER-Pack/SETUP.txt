JM THUNDER GOLD SCALPER V1.0.0
==============================

Bagong EA. Hindi V6.1 at hindi V6.77.
Isang file lang. F7 this only.

RULES
-----
  NO grid
  NO martingale
  NO averaging / hedge
  Isang trade lang at a time
  Hard SL + TP sa bawat order

ENTRY (THUNDER)
---------------
  1) M5 EMA20/50 + ADX bias
  2) THUNDER = last closed M5 broke prior swing high/low
  3) M1 small-candle compression tapos break ng wick
  4) M1 EMA9/21 agrees, RSI zone, score >= 3
  5) V640 hours (same profitable hours as your V6.77)

DEFAULTS
--------
  Symbol   GOLD#
  Lots     0.01
  Magic    26100610
  SL       $15 @ 0.01 (scales with lot)
  TP       $30, or $45 kung strong ADX+gap
  Broker   UTC+3 (XM)

INSTALL
-------
1. MT5 -> File -> Open Data Folder
2. Copy JM_THUNDER_GOLD_SCALPER.mq5 -> MQL5\Experts\
3. MetaEditor -> F7 (0 errors)
4. Tanggalin ang ibang gold EA sa GOLD# chart (isang EA lang)
5. Drag Thunder sa GOLD# chart
6. Algo Trading ON (green)
7. DEMO / Strategy Tester muna. Every tick. M1 + M5 history.

PANEL
-----
  BIAS BUY/SELL = M5 trend, hindi pa entry
  THUNDER: YES  = may swing break
  Small M1: YES = may compression candle
  Status        = bakit WAIT / bakit OPEN

HUWAG
-----
- Dalawang gold EA sa iisang chart
- Live / real hangga't hindi tapos ang demo retest
- Palitan ang V6.1 file
- I-on ang grid/martingale (wala naman sa code)
