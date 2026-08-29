JM FX Complete Windows Pack
===========================

Lahat ng kailangan para sa MT5 (DDDC3D) + MT4 demo + MT4 real sa Windows PC.

DIRECT DOWNLOAD (GitHub)
------------------------
Full ZIP (lahat ng files + Python):
  https://github.com/jmmwireless99-dotcom/JM-Forex-Trading/raw/main/releases/JM-FX-Complete-Pack.zip

Cloud mirror:
  https://jmtechsolution.cloud/fx/api/downloads/jmfx-complete.zip

CONTENTS
--------
  install-python.bat       → i-install ang Python (kung wala pa)
  install-python.ps1       → PowerShell installer script
  python/                  → portable Python (embed) — ready after unzip
  start-jm-mt5-agent.bat   → PC agent gamit bundled Python
  pc-agent/                → MT5 sync agent (legacy mode)
  mt5/                     → JM_Forex_Bridge.mq5 v2 (cloud, walang agent)
  mt4/                     → JM_Forex_Bridge.mq4 (demo + real)
  docs/                    → setup guides
  accounts/                → JM FX login info

QUICK START — MT5 (DDDC3D, recommended, walang agent)
-------------------------------------------------------
1. Unzip ang buong folder
2. MT5 → MQL5\Experts\ → kopyahin mt5\Experts\JM_Forex_Bridge.mq5 → Compile F7
3. MT5 → Tools → Options → Expert Advisors:
     Allow WebRequest → add: https://jmtechsolution.cloud
4. Attach EA sa GOLD# chart:
     InpUseCloudBridge = true
     InpBridgeToken = (see accounts\JM-FX-ACCOUNTS.txt)
5. Login: https://jmtechsolution.cloud/fx/  Code: DDDC3D

QUICK START — MT4 Real
----------------------
1. MT4 → MQL4\Experts\ → kopyahin mt4\Experts\JM_Forex_Bridge.mq4 → Compile F7
2. Attach sa XAUUSD chart, UseCommonFolder=true
3. Set JM_MT4_REAL_BRIDGE_DIR sa server .env (hiwalay folder sa demo/MT5)
4. Login gamit MT4 real account code + token (see accounts\JM-FX-ACCOUNTS.txt)

QUICK START — PC Agent (legacy MT5 sync)
----------------------------------------
1. Double-click install-python.bat (kung wala pang Python)
   O gamitin ang bundled python\ folder
2. Double-click start-jm-mt5-agent.bat
3. Keep window open habang naka-open ang MT5 + EA

See docs\ folder for full guides.
