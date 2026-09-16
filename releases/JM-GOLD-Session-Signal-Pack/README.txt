JM GOLD SESSION SIGNAL v1.25 — indicator only
=============================================

Hindi EA. Walang OrderSend.

SIGNAL FLOW (closed M5 bar, hindi nagre-repaint)
------------------------------------------------
Dot lalabas LANG kung PASOK lahat:

1. EMA 50 side     close above EMA = BUY, below = SELL
2. Candle confirm  bull candle = BUY, bear = SELL
3. RSI 14          BUY: 45-70 and rising    SELL: 30-55 and falling
4. BB bounce       BUY: wick hits lower band, close back above
                   SELL: wick hits upper band, close back below
5. H1 trend        H1 EMA20 vs EMA50 same side as the entry

H4 at M15 = display lang (filter OFF).
Sessions (ASIAN/LONDON/NY) = kulay at pangalan, hindi filter.
PH oras = yellow sa taas ng hour candle.

Maliit na DOT: aqua BUY sa ilalim, magenta SELL sa taas.
Hindi na yung malalaking arrow.

Kung walang dot: walang confirmed setup. Huwag i-on InpEasyArrows
maliban kung gusto mong i-debug (EMA+candle flood).

INSTALL
-------
1. Copy mq5 → MQL5\Indicators\ (hindi Experts)
2. MetaEditor → F7
3. Copy tpl → MQL5\Profiles\Templates\
4. Delete old indicator on chart
5. Templates → JM_GOLD_Session_M5

CSV: MQL5\Files\JM_GOLD_Session_Signal_v1.csv
Demo/tester muna. Huwag i-attach kasama ng V6.1.
