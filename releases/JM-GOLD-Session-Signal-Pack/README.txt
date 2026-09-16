JM GOLD SESSION SIGNAL v1 — indicator only
==========================================

Hindi EA. Walang OrderSend. Visual validation muna sa GOLD# chart.

DALAWANG TRABAHO
----------------
1) PH sessions (UTC+8)
   Daily 00:00–23:59
   Asian/Tokyo  08:00–16:00 PH
   London       15:00–00:00 PH
   New York     20:00–05:00 PH
   London–NY overlap 20:00–00:00 PH
   Colored transparent zones + session-open lines + live PH clock panel

2) Signal arrows (closed bar, hindi nagre-repaint)
   Chart TF = entry (M5 recommended, M1 OK)
   EMA 50 trend + RSI momentum + Bollinger bounce + candle confirm
   H1 trend filter ON by default
   H4 + M15 = display / optional filter (OFF by default para hindi gutom)

INSTALL
-------
1. Copy JM_GOLD_Session_Signal_v1.mq5 → MQL5\Indicators\
2. MetaEditor → F7 (0 errors)
3. GOLD# chart, M5 (or M1)
4. Navigator → Indicators → i-drag sa chart (HINDI Experts)
5. Allow DLL: hindi kailangan. CSV isusulat sa MQL5\Files\

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
1. Scroll history — arrows ba tumatama sa pullback/bounce?
2. I-on InpRequireM15 o InpRequireH4 kung sobrang dami
3. I-off InpRequireH1 kung sobrang konti
4. Strategy Tester → Visual mode sa indicator (hindi Expert)
5. Pag OK na ang arrows, saka natin i-convert sa EA (huwag muna)

HUWAG
-----
- I-attach kasama ng gold EA kung magulo ang chart (panel Comment)
- Live auto-trade — wala namang order dito
