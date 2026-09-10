JM GOLD EMA200 + STOCHASTIC SCALPER
===================================

Malinis na chart: 2 indicators lang.
Hindi ito ang V6.1. Huwag i-attach kasama ng V6.1 sa iisang GOLD# chart.

STRATEGY
--------
Timeframe data: M1 (kahit M5 chart, M1 candles ang ginagamit)
Indicator 1: EMA 200  — price above = BUY only, below = SELL only
Indicator 2: Stochastic 5,3,3
  BUY:  small red pullback → Stoch below 20 → K cross up + small green
  SELL: small green pullback → Stoch above 80 → K cross down + small red

MONEY (GOLD PRICE $, hindi account P/L)
---------------------------------------
Sa Gold, $1.00 galaw ng presyo = 10 pips.

  SL     $3.50 behind entry   (pwede 2.00–5.00)
  TP1    +$5    close ~50% (0.01 ng 0.03) + SL → breakeven
  TP2    +$10   close next 0.01
  TP3    +$15   close the rest (hard TP on the order)

Lots: 0.03 para may 3 legs (0.01 + 0.01 + 0.01).
      0.01 lot = walang scale-out (broker min). Close-all sa TP1.

SESSION / NEWS
--------------
NY session ON: broker hour 14–23 (XM GMT+2 ≈ 8:00 PM onwards PH)
First-Friday NFP: auto-block hours 14–17
CPI / FOMC: MANUAL — huwag mag-scalp 15 min before/after high-impact US news
Spread: raw/low gold spread. Malaking spread = talo ka sa $2–$5 targets.

INSTALL (F7)
------------
1. MT5 → File → Open Data Folder
2. Copy JM_GOLD_EMA200_STOCH_SCALPER.mq5 → MQL5\Experts\
3. MetaEditor → F7 (one file, 0 errors)
4. Detach V6.1 / other gold EAs from GOLD#
5. Attach this EA to GOLD# (M1 recommended)
6. Inputs: GOLD#, lots 0.03, Algo Trading ON
7. Demo first. Same dates sa Strategy Tester (Every tick) bago i-compare sa V6.1

HUWAG
-----
- Dalawang gold EA sa iisang chart
- Live / Optimize hanggang mag-match ang demo sa tester
- Palitan TP/SL sa unang linggo ng demo
