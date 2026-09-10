JM Lab XAUUSD — MT5 Expert Advisor Pack
========================================

Strategy source: https://jmtechsolution.cloud/lab/XAUUSD
Matches Lab preset EMA_RSI_TREND (paper demo engine).

STRATEGY RULES (M5)
-------------------
- EMA 20 / EMA 50 trend filter
- RSI 14
- BUY:  EMA20 > EMA50 AND RSI 36–55
- SELL: EMA20 < EMA50 AND RSI 45–64
- SL / TP: 50 pips each (pip = 0.01 for gold)
- Lot size: 0.03 (adjust in EA inputs)
- Max spread: 3.5 pips
- One position at a time
- 3 M5 bars minimum between entries
- 4 M5 bar cooldown after a losing trade
- Signal evaluated on each new M5 bar close

DOWNLOAD (browser)
------------------
ZIP:  https://jmtechsolution.cloud/lab/api/downloads/lab-xauusd-ea.zip
EA:   https://jmtechsolution.cloud/lab/api/downloads/JM_Lab_XAUUSD_EA.mq5
Links: https://jmtechsolution.cloud/lab/api/downloads/lab-xauusd-ea

QUICK START (Windows / MT5)
---------------------------
1. Install MetaTrader 5 and log in to your broker account.

2. Copy Experts/JM_Lab_XAUUSD_EA.mq5
   → MT5: File → Open Data Folder → MQL5/Experts/
   → Open in MetaEditor → Compile (F7) — zero errors

3. Open M5 chart for your gold symbol (examples):
   - XM:        GOLD# or XAUUSD
   - Other:     XAUUSD, GOLD, XAUUSDm

4. Drag JM_Lab_XAUUSD_EA onto the M5 chart.

5. Recommended inputs:
   - InpSymbol     = (blank = chart symbol) or GOLD#
   - InpLots       = 0.03
   - InpSlPips     = 50
   - InpTpPips     = 50
   - InpPipSize    = 0.01  (gold)
   - InpMaxSpreadPips = 3.5

6. Enable Algo Trading (green button in MT5 toolbar).

7. EA shows live status on chart (EMA, RSI, spread, block reason).

IMPORTANT
---------
- This EA runs the strategy LOCALLY on your MT5 — no cloud connection required.
- It is NOT the JM FX bridge (DDDC3D). Lab paper results may differ slightly
  from live broker fills, spread, and EMA/RSI rounding.
- Test on DEMO first. Adjust lot size to your account risk.
- Gold pip size: if SL/TP look wrong, set InpPipSize to match your broker
  (usually 0.01 for 2-digit gold quotes).

TROUBLESHOOTING
---------------
No trades?     → Check M5 chart, Algo Trading ON, spread under 3.5 pips
Wrong SL/TP?   → Verify InpPipSize = 0.01 and InpSlPips/InpTpPips = 50
Compile error? → Use MT5 build 3000+ with standard Trade library

SUPPORT
-------
Lab desk: https://jmtechsolution.cloud/lab/XAUUSD
