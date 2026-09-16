JM GOLD SESSION SIGNAL v1.26 — indicator only
=============================================

Hindi EA. Walang OrderSend.

ANO ANG MAKIKITA
----------------
Gold/yellow LINE = EMA50 BIAS
  Price above line = BUY bias
  Price below line = SELL bias
  Text sa dulo: BIAS BUY o BIAS SELL

Aqua DOT + "BUY"  = confirmed BUY  (sa ILALIM ng price)
Magenta DOT + "SELL" = confirmed SELL (sa TAAS ng price)

Kung Last signal: none yet — wala pang pasok sa checklist.
Yung maliliit na arrow/X ng MT5 trade history HINDI iyon ang signal natin.

SIGNAL FLOW (closed M5 candle)
------------------------------
1. EMA 50 side     close vs gold bias line
2. Candle confirm  bull = BUY, bear = SELL
3. RSI 14          BUY 45-70 rising / SELL 30-55 falling
4. BB bounce       wick to band, close back inside
5. H1 trend        same side

Gamitin ang CANDLE chart (hindi line chart) para makita ang BB wick.

INSTALL
-------
1. mq5 → MQL5\Indicators\  F7
2. Delete old indicator on chart
3. Templates → JM_GOLD_Session_M5
   o Charts → Candlesticks kung line chart ang naka-on
