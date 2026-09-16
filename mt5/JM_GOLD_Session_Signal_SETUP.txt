JM GOLD SESSION SIGNAL v1.20 — indicator only
=============================================

Hindi EA. Walang OrderSend. Visual validation muna sa GOLD# chart.

ANO ANG DAPAT MO MAKITA
-----------------------
1) Name sa bawat kulay na column
   ASIAN    gold
   LONDON   asul
   NEW YORK berde
   OVERLAP  lila
2) PH oras sa dulo ng candle wick (puti): 12AM, 1AM, ... 1PM, 2PM
3) BUY ▲ (lime) / SELL ▼ (pula) arrows — Easy arrows ON (EMA + candle)

Kung wala pa ring name / oras / arrow: lumang .ex5 ang naka-attach.
Tanggalin ang indicator sa chart, F7 ulit, tapos i-load ang M5 template.

PH SESSIONS (UTC+8)
-------------------
Daily 00:00–23:59 (white midnight line)
Asian/Tokyo  08:00–16:00 PH
London       15:00–00:00 PH
New York     20:00–05:00 PH
London–NY overlap 20:00–00:00 PH

SIGNAL (closed bar, hindi nagre-repaint)
----------------------------------------
Default Easy arrows = EMA 50 + candle confirm lang para may makita kang arrow.
I-off InpEasyArrows pag gusto mo na ng RSI + BB + H1 filter.

INSTALL
-------
1. Copy JM_GOLD_Session_Signal_v1.mq5 → MQL5\Indicators\
2. MetaEditor → F7 (0 errors) — kailangan muna .ex5 bago template
3. Copy Templates\*.tpl → MQL5\Profiles\Templates\
4. GOLD# chart → right-click chart → Indicators List → DELETE old session signal
5. Right-click → Templates → JM_GOLD_Session_M5
   (M1 template: JM_GOLD_Session_M1)
6. CSV: MQL5\Files\JM_GOLD_Session_Signal_v1.csv

TEMPLATE FILES
--------------
  Templates/JM_GOLD_Session_M5.tpl
  Templates/JM_GOLD_Session_M1.tpl
  Templates/APPLY-TEMPLATE.txt

SIGNAL CARD
-----------
BUY ▲
PH TIME: 9:17 PM
SESSION: NEW YORK
H1 TREND: BUY
M15 MOMENTUM: BUY
ENTRY: 3684.50

CSV (para sa future EA)
-----------------------
MQL5\Files\JM_GOLD_Session_Signal_v1.csv
Columns: time, session, side, entry, h4, h1, m15, ema, rsi, bb, candle, reason

PAANO I-VALIDATE
----------------
1. Scroll history — names ba nakasulat sa column? hours ba nasa wick? arrows ba may BUY/SELL?
2. I-off InpEasyArrows, i-on InpRequireH1 kung gusto mas filter
3. Strategy Tester → Visual mode sa indicator (hindi Expert)
4. Pag OK na ang arrows, saka natin i-convert sa EA (huwag muna)

HUWAG
-----
- I-attach kasama ng gold EA kung magulo ang chart (panel Comment)
- Live auto-trade — wala namang order dito
