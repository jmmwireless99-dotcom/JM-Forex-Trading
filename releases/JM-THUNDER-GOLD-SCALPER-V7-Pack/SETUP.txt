JM THUNDER GOLD SCALPER V7
=========================================

Bagong EA. Hindi V6.1 / V6.77.
File: JM_THUNDER_GOLD_SCALPER_V7.mq5
F7 this only. Demo muna.

V7 — BILIS
--------------------
  FastEntry ON  = bawat tick bina-basa ang chart / ina-update ang pending
  FastTrail ON  = trailing sumusunod sa EXTREME (pinakataas/baba ng pitik)
  Trail step 0  = walang antay-antay; agad i-modify ang SL
  TrailReplacesSL = kapag naka-trail na, SL = trailing stop na
                    (lumang malayong SL hindi na gamit)
  Halimbawa BUY: price pumitik 2010 tapos bumaba —
                 SL mananatili ~2009.30 (2010 - $0.70) para harangin
                 ang dulo ng move.

RULES
-----
  NO grid / NO martingale / NO averaging
  Auto Thunder = ON palagi
  Manual STOP/LIMIT = trail after fill ($0.50 start / $0.70 distance)

DALAWANG FLOW
-------------
  A) AUTO — M15 swing BUY/SELL STOP + trail
  B) MANUAL — ikaw mag-pending + SL/TP; pag fill, fast trail

DEFAULTS
--------
  Version  7
  Magic    30250007
  Trail    start $0.50 / dist $0.70 / step every tick
  FastEntry / FastTrail / TrailReplacesSL = ON

INSTALL — DESKTOP
-----------------
1. Double-click COPY-TO-DESKTOP.bat
2. MetaEditor F7
3. Attach V7 sa gold chart, Algo Trading ON
4. DEMO muna

HUWAG
-----
- Dalawang gold EA sa iisang chart
- Live bago matapos ang demo
