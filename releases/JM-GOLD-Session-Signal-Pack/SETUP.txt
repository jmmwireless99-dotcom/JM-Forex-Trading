JM GOLD SESSION SIGNAL v1.31 — indicator only
=============================================

Hindi EA. Walang OrderSend.

SAAN MAKIKITA ANG ENTRY
-----------------------
Sa TAAS ng candle (wick):

  lime DOT + "BUY"   = ENTRY BUY
  red  DOT + "SELL"  = ENTRY SELL
  yellow/orange "o"  = strategy setup, pero V640 hour OFF (huwag i-trade)

Panel: LAST: BUY at 1:15 PM PH  |  dots=N
Kung dots=0, wala pang closed-bar setup sa loaded history.

SIGNAL FLOW
-----------
V6.77 M5 EMA/ADX/gap + small-candle break + M1 flow/RSI/score>=3
+ H1 required + M30 required. H4 display only.

Ngayon (screenshot): V640 both OFF sa broker H14 / 7:35 PM PH
  = walang lime/red entry sa oras na ito. Hintay 10PM PH BUY hour
    o yellow "o" kung may setup na naka-block ng hour.

INSTALL
-------
1. mq5 → MQL5\Indicators\  F7  (Indicators folder)
2. Delete OLD indicator on chart (important)
3. Templates → JM_GOLD_Session_M5
4. Hintay 1-2 segundo kung "M1 bars" sa panel umakyat (M1 loading)
