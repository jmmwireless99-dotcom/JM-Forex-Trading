JM THUNDER GOLD SCALPER V7.0
============================

Bagong EA (M15 structure + manual trail). Hindi V6.1 / V6.77 / V2.0.3 file name.
Isang file: JM_THUNDER_GOLD_SCALPER_V7.mq5
F7 this only. Demo / tester muna.

RULES
-----
  NO grid
  NO martingale
  NO averaging / hedge
  Auto Thunder = ON palagi (hindi naka-pause)
  Manual = ikaw mag-lagay ng BUY/SELL STOP o LIMIT + sariling SL/TP
  Pag na-fill: EA trail lang ang SL (simula +$0.50, distance $0.70)

DALAWANG FLOW
-------------
  A) AUTO THUNDER — palaging ON
     M15 unbroken swing -> BUY STOP / SELL STOP
     EMA20/200, RSI, candle, volume
     EA SL/TP + trailing

  B) MANUAL ENTRY TRAIL — dagdag lang
     1. Attach V7 sa chart, Algo Trading ON
     2. Maglagay ng BUY/SELL STOP o LIMIT + SL/TP mo
     3. Pag na-fill: trail mula +$0.50 @ 0.01, distance $0.70
     4. Hindi papalitan ang SL/TP mo
     5. Auto Thunder TULOY pa rin

DEFAULTS
--------
  File     JM_THUNDER_GOLD_SCALPER_V7.mq5
  Version  7.00
  Magic    30250007
  Manual   magic 0
  Trail    start $0.50 / dist $0.70 / step $0.10
  Symbol   GOLD# o Vantage XAUUSD / XAUUSDm

INSTALL — DESKTOP + VANTAGE
---------------------------
1. I-double click COPY-TO-DESKTOP.bat
   -> lalagay ang EA sa Desktop\JM-THUNDER-GOLD-SCALPER-V7\
   -> at sa MQL5\Experts ng Vantage/MT5 kung nahanap
2. O manual: copy JM_THUNDER_GOLD_SCALPER_V7.mq5 -> MQL5\Experts\
3. MetaEditor F7 (0 errors)
4. Isang EA lang sa chart. Attach V7. Algo Trading ON.
5. DEMO muna.

HUWAG
-----
- Dalawang gold EA sa iisang chart
- Live hangga't hindi tapos demo
- Palitan ang V6.1 / V6.77 files
