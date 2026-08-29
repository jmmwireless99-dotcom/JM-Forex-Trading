JM FX — XM MT5 Bridge Pack (Aug 28 2026)
=========================================

Para sa MT5 login: 169250320 (XM Demo) · JM account: DDDC3D

DIRECT DOWNLOADS (browser)
--------------------------
Full ZIP:     https://jmtechsolution.cloud/fx/api/downloads/mt5-bridge.zip
Bridge EA:    https://jmtechsolution.cloud/fx/api/downloads/JM_Forex_Bridge.mq5
PC Agent:     https://jmtechsolution.cloud/fx/api/downloads/jm_mt5_pc_agent.py
Start BAT:    https://jmtechsolution.cloud/fx/api/downloads/start-jm-mt5-agent.bat
All links:    https://jmtechsolution.cloud/fx/api/downloads/mt5-bridge

QUICK START (Windows PC — NO AGENT, recommended)
-----------------------------------------------
1. Install XM MT5 + login (169250320)

2. Copy Experts/JM_Forex_Bridge.mq5 → MQL5/Experts/ → Compile (v2.00)

3. MT5 → Tools → Options → Expert Advisors:
   - Allow WebRequest → add: https://jmtechsolution.cloud

4. Attach EA sa GOLD# chart:
   - InpSymbol = GOLD#
   - InpUseCloudBridge = true
   - InpBridgeToken = gTXmD7O-194jS9gveB1I5c9qjmNdqdUv
   - Algo Trading ON

5. HUWAG buksan ang PC agent (start-jm-mt5-agent.bat)

6. Login sa https://jmtechsolution.cloud/fx/
   Code DDDC3D + token (see JM-FX-ACCOUNT.txt)

7. Dapat MT online (green) within ~5 sec

Full guide: docs/MT5_NO_AGENT_SETUP.md in repo

QUICK START (legacy — PC agent, optional fallback)
--------------------------------------------------
1. Install XM MetaTrader 5 at mag-login (169250320 + password sa MT5 lang).

2. Copy Experts/JM_Forex_Bridge.mq5
   → MT5: File → Open Data Folder → MQL5/Experts/
   → MetaEditor: Compile (F7), zero errors

3. Drag JM_Forex_Bridge sa GOLD# chart
   → InpSymbol = GOLD# (XM gold symbol)
   → UseCommonFolder = true
   → InpPollMs = 100
   → Algo Trading ON (green)

4. Double-click pc-agent/start-jm-mt5-agent.bat
   → Dapat tumakbo ang sync papuntang https://jmtechsolution.cloud/fx/
   → Huwag isara ang window

5. Sa browser: https://jmtechsolution.cloud/fx/
   → Sign in:
     Code:  DDDC3D
     Token: (see JM-FX-ACCOUNT.txt)

6. Dapat MT5 LIVE / MT online sa dashboard (~5 sec after agent starts)

FILES
-----
Experts/JM_Forex_Bridge.mq5   — EA para sa MT5 (GOLD# auto-resolve)
pc-agent/jm_mt5_pc_agent.py   — Sync agent (Python 3, 80ms command poll)
pc-agent/start-jm-mt5-agent.bat — Double-click launcher
XM_MT5_SETUP.md               — Full step-by-step guide
JM-FX-ACCOUNT.txt             — DDDC3D login token

TROUBLESHOOTING
---------------
MT offline?  → Restart BAT + check Algo Trading ON
XAUUSD,0.00? → Recompile EA, InpSymbol=GOLD#
Order reject?→ Market open? Lots OK? EA compiled?

SUPPORT
-------
Desk: https://jmtechsolution.cloud/fx/
