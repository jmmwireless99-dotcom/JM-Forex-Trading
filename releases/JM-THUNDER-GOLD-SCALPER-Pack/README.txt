JM THUNDER GOLD SCALPER V2.0.3
==============================

Bagong EA (M15 structure + manual trail). Hindi V6.1 at hindi V6.77.
Isang file lang. F7 this only. Demo / tester muna.

RULES
-----
  NO grid
  NO martingale
  NO averaging / hedge
  Auto = isang Thunder pending side at a time
  Manual = ikaw mag-lagay ng BUY/SELL STOP o LIMIT + sariling SL/TP

DALAWANG FLOW
-------------
  A) AUTO THUNDER
     M15 unbroken swing high/low -> BUY STOP / SELL STOP
     EMA20/200 trend, RSI, candle, volume
     EA SL/TP + trailing

  B) MANUAL ENTRY (ikaw)
     1. Chart GOLD# / XAUUSD, Thunder naka-attach, Algo Trading ON
     2. Maglagay ng BUY STOP, SELL STOP, BUY LIMIT, o SELL LIMIT
     3. Lagyan ng SL at TP na gusto mo (hindi papalitan ng EA)
     4. Pag na-TRIGGER / na-fill:
        - EA maglalagay ng trailing stop
        - Start: +$0.50 gold @ 0.01 lot
        - Distance: original Thunder pullback $0.70 (70 pts)
        - Step: $0.10 (10 pts)
        - Susundan ang galaw; pag nag-pullback ng $0.70, SL hit
     5. Habang may manual pending o open position, pause ang auto Thunder stops

TRAILING (parehong auto at manual fill)
---------------------------------------
  Default start    $0.50  @ 0.01 lot   (50 pts GOLD 2-digit)
  Default distance $0.70               (70 pts — original Thunder)
  Default step     $0.10               (10 pts)
  Inputs: InpTrailStartUsd / InpTrailDistanceUsd / InpTrailStepUsd
  InpTrailStart / InpTrailDistance / InpTrailStep = 0  -> gamitin ang USD values
  Manual SL/TP: KEEP (InpManualKeepStops=true). EA trail lang ang SL sa profit.

DEFAULTS
--------
  Symbol        GOLD#  (o XAUUSD)
  Magic auto    30250003
  Magic manual  0  (MT5 default kapag ikaw nag-click)
  Lots auto     risk % o InpFixedLot 0.01
  SL auto       $2 @ 0.01 kung InpSLPoints=0
  Trail start   $0.50
  Trail dist    $0.70
  Session GMT   08:00-21:00

INSTALL — VANTAGE MT5 (Windows)
-------------------------------
Pinakamadali: i-double click COPY-TO-VANTAGE-MT5.bat
  -> kokopyahin ang EA sa MQL5\Experts ng Vantage terminal.

Manual:
1. Vantage MT5 -> File -> Open Data Folder
2. Punta sa MQL5\Experts\
3. Copy JM_THUNDER_GOLD_SCALPER.mq5 doon
4. MetaEditor -> F7 (0 errors)
5. Tanggalin ang ibang gold EA sa chart (isang EA lang)
6. Drag Thunder sa XAUUSD / XAUUSDm chart (Vantage symbol, hindi GOLD#)
7. Inputs: Manual Entry Trail = ON, Pause Auto When Manual = ON, Keep SL/TP = ON
8. Algo Trading ON (green)
9. DEMO muna. Every tick. M15 history.

Kung Vantage MT4 iyan: HINDI tatakbo ang .mq5. Kailangan Vantage MT5.

PANEL
-----
  TRAIL $0.50 / $0.70 = start / pullback distance
  MANUAL READY        = pwedeng mag-pending ikaw
  MANUAL TRAILING     = may fill / pending mo, auto pause, trail ON
  MANUAL SL/TP KEEP   = hindi overwrite ang stops mo
  SYSTEM MANUAL TRAIL = auto Thunder naka-pause

HUWAG
-----
- Dalawang gold EA sa iisang chart
- Live / real hangga't hindi tapos ang demo retest
- Palitan ang V6.1 o V6.77 file
- I-on ang grid/martingale (wala naman sa code)
- Ibura ang SL/TP mo bago mag-trail — kailangan nila para protektahan bago +$0.50
