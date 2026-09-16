JM GOLD SESSION SIGNAL v1.30 — indicator only
=============================================

Hindi EA. Walang OrderSend. Hindi kapalit ng V6.77 / V6.1 expert.

PAANO MALALAMAN BUY O SELL
--------------------------
Gold line = M5 EMA50 BIAS (trend lang, hindi entry).
Aqua line = M5 EMA20.

Entry signal:
  lime "BUY"  + lime dot  = sa ILALIM ng candle  -> BUY
  red  "SELL" + red dot   = sa TAAS ng candle    -> SELL

Panel: LAST SIGNAL: BUY at 1:15 PM PH  (o SELL...)
Kung none yet, wala pang confirmed scalper setup.

SIGNAL FLOW (V6.77 scalper analog, closed bars)
----------------------------------------------
1. M5 EMA20/50 + ADX + GapATR   same as JM GOLD SCALPER V6.77
2. V641/V642/V643 blocks        mid ADX, weak/strong gap classes
3. M1 small candle              compression bar (body/range vs ATR)
4. M1 closed break              high/low beyond small candle + ATR buffer
5. M1 EMA9/21 flow + RSI zone   BUY 46-68 / SELL 32-54
6. Flow score >= 3
7. V640 profit hours            server hours from V6.77
8. H1 EMA20/50 REQUIRED         same side (blocks selling the lows vs H1 BUY)
9. M30 EMA20/50 REQUIRED        same side (bridge M5 -> H1)
10. H4 EMA20/50 DISPLAY only    panel + H4 SR lines, not a hard filter

Bakit H1 + M30, H4 display lang
-------------------------------
H1 ang "tumalikod na ba ang hour?" gate.
M30 ang confirmation na malapit sa scalper, hindi kasing-bagal ng H4.
H4 masyadong mabagal para sa GOLD scalp — kita sa panel, hindi blocker.

INSTALL
-------
1. mq5 → MQL5\Indicators\  F7  (Indicators folder, hindi Experts)
2. Delete old indicator on chart
3. Templates → JM_GOLD_Session_M5
   o Charts → Candlesticks kung line chart ang naka-on
4. Demo/tester muna. Walang auto trade.

NEXT CLICKS
-----------
F7 compile → attach GOLD# M5 → wait closed M1 break inside a V640 hour
→ lime BUY under / red SELL above. Compare vs V6.77 tester entries.
