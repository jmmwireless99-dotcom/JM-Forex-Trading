JM MTF Volume Profile Scalper v1.30
====================================

Multi-timeframe gold scalper: H1 trend → M15 volume POC zone + small candle → M1 BOS entry.

FLOW
----
1. H1: EMA 50/200 trend filter (bullish / bearish)
2. M15: Volume profile POC + ATR zone; small body + rejection wick at zone
3. M1: Strong candle break of structure + signal candle high/low
4. SL: beyond M15 signal wick + buffer · TP: RiskReward × SL distance

INSTALL (MT5)
-------------
1. Copy Experts/JM_MTF_Volume_Profile_Scalper.mq5 → MQL5/Experts/
2. MetaEditor → Compile (F7)
3. Attach to XAUUSD / GOLD# chart (M1 chart — EA reads H1/M15 internally)
4. Chart: volume histogram (left), M15 POC zone, H1 supply/demand, order blocks
5. EnableAutoTrading = false → signals + lines only (Experts log)
6. EnableAutoTrading = true + Algo Trading ON → live orders

CHART INPUTS (v1.30)
--------------------
ShowVolumeHistogram, ShowOrderBlocks, ShowH1SupplyDemand
HistogramMaxMinutes — how far VP bars extend horizontally

RECOMMENDED (gold)
------------------
- MaxSpreadPoints: 350 (adjust for broker digits)
- Lots: 0.01 demo first
- RiskReward: 2.0 (default)

JM FX DESK
----------
This EA runs locally on MT5. It is NOT the JM_Forex_Bridge cloud desk.
Do not run both on the same symbol unless you intend duplicate logic.

SOURCE
------
mt5/Experts/JM_MTF_Volume_Profile_Scalper.mq5
