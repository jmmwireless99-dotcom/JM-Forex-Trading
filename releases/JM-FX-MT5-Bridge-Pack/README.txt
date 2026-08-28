JM FX — XM MT5 Bridge Pack
==========================

Para sa MT5 login: 169250320 (XM Demo)

QUICK START (Windows PC)
------------------------
1. Install XM MetaTrader 5 at mag-login (169250320 + password sa MT5 lang).

2. Copy Experts/JM_Forex_Bridge.mq5
   → MT5: File → Open Data Folder → MQL5/Experts/
   → MetaEditor: Compile (F7), zero errors

3. Drag JM_Forex_Bridge sa GOLD# chart
   → InpSymbol = GOLD# (XM gold symbol)
   → UseCommonFolder = true
   → Algo Trading ON (green)

4. Double-click pc-agent/start-jm-mt5-agent.bat
   → Dapat tumakbo ang sync papuntang https://jmtechsolution.cloud/fx/

5. Sa browser: https://jmtechsolution.cloud/fx/
   → Sign in:
     Code:  DDDC3D
     Token: (see JM-FX-ACCOUNT.txt)

6. Kapag MT online na sa dashboard, piliin mt5 → Apply mode.

FILES
-----
Experts/JM_Forex_Bridge.mq5   — EA para sa MT5
pc-agent/jm_mt5_pc_agent.py   — Sync agent (Python 3)
pc-agent/start-jm-mt5-agent.bat — Double-click launcher
XM_MT5_SETUP.md               — Full step-by-step guide

SUPPORT
-------
Desk: https://jmtechsolution.cloud/fx/
Bridge token at server config naka-set na sa cloud.
