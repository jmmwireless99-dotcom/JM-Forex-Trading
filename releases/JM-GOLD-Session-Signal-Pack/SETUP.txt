JM GOLD SESSION SIGNAL v1.23 — indicator only
=============================================

Hindi EA. Walang OrderSend. Visual validation muna sa GOLD# chart.

ANO ANG DAPAT MO MAKITA (gaya ng sample chart)
----------------------------------------------
1) Dilaw na PH oras sa TAAS ng bawat hour candle: 8AM, 9AM, 1PM, 2PM…
   (nakatayo ang text sa itaas ng kandila)
2) BUY ▲ cyan/aqua sa ilalim ng candle
   SELL ▼ magenta sa taas ng candle
3) ASIAN / LONDON / NEW YORK / OVERLAP name sa column
   (banayad na kulay lang — hindi tinatakpan ang candles)

Hindi kasama sa pack ang rainbow MA / TVI sa sample screenshot.
Ito ay session + hour + arrow template lang.

Kung wala pa ring oras / arrow: lumang .ex5. Delete indicator, F7, load M5 template.

PH SESSIONS (UTC+8)
-------------------
Asian/Tokyo  08:00–16:00 PH
London       15:00–00:00 PH
New York     20:00–05:00 PH
London–NY overlap 20:00–00:00 PH

SIGNAL
------
Easy arrows ON = EMA 50 + candle confirm. Lalabas ang BUY/SELL gaya ng sample.
I-off InpEasyArrows pag gusto mo na ng RSI + BB + H1 filter.

INSTALL
-------
1. Copy JM_GOLD_Session_Signal_v1.mq5 → MQL5\Indicators\
2. MetaEditor: buksan mula sa MQL5\Indicators\ (HUWAG Experts) → F7 (0 errors)
3. Copy Templates\*.tpl → MQL5\Profiles\Templates\
4. GOLD# chart → Indicators List → DELETE old session signal
5. Right-click → Templates → JM_GOLD_Session_M5
6. CSV: MQL5\Files\JM_GOLD_Session_Signal_v1.csv

PAANO I-VALIDATE
----------------
1. Black chart, white/red candles
2. Yellow 1PM/2PM sa taas ng hour candles
3. Cyan BUY at magenta SELL arrows sa price
4. Strategy Tester → Visual mode sa indicator (hindi Expert)
5. Pag OK na, saka EA (huwag muna)

HUWAG
-----
- I-attach kasama ng gold EA kung magulo ang chart
- Live auto-trade — wala namang order dito
