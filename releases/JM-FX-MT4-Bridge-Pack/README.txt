JM FX — XM MT4 Bridge Pack
==========================

DIRECT DOWNLOADS (browser)
--------------------------
Full ZIP:     https://jmtechsolution.cloud/fx/api/downloads/mt4-bridge.zip
EA v2 ZIP:    https://jmtechsolution.cloud/fx/api/downloads/mt4-ea-v2.zip
Real EA ZIP:  https://jmtechsolution.cloud/fx/api/downloads/mt4-real-ea-v2.zip
Bridge EA:    https://jmtechsolution.cloud/fx/api/downloads/JM_Forex_Bridge.mq4
All links:    https://jmtechsolution.cloud/fx/api/downloads/mt4-bridge

QUICK START — MT4 REAL (cloud, walang PC agent) — RECOMMENDED
---------------------------------------------------------------
1. Install XM MT4 REAL + login sa live account

2. Copy Experts/JM_Forex_Bridge.mq4 → MQL4/Experts/ → Compile (F7, v2.00)

3. MT4 → Tools → Options → Expert Advisors:
   - Allow automated trading
   - Allow WebRequest → add: https://jmtechsolution.cloud

4. Attach EA sa XAUUSD (o GOLD) chart:
   - InpSymbol = XAUUSD  (exact broker symbol)
   - InpUseCloudBridge = true
   - InpBridgeToken = gTXmD7O-194jS9gveB1I5c9qjmNdqdUv
   - AutoTrading ON

5. Login sa https://jmtechsolution.cloud/fx/
   Code + Token: see JM-FX-MT4-ACCOUNTS.txt (MT4 REAL account)

6. Check: https://jmtechsolution.cloud/fx/api/mt4/real/status
   Dapat "online": true

QUICK START — MT4 DEMO (local file bridge)
------------------------------------------
1. Install XM MT4 DEMO + login

2. Copy Experts/JM_Forex_Bridge.mq4 → MQL4/Experts/ → Compile (F7)

3. Attach EA sa chart:
   - InpSymbol = GOLD  (XM MT4 demo gold symbol)
   - InpUseCloudBridge = false
   - UseCommonFolder = true
   - AutoTrading ON

4. Common Files folder:
   C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\Common\Files

5. Server .env: JM_MT4_BRIDGE_DIR=<same path> + JM_MT4_DEMO_ACCOUNT_CODE

6. Login sa JM FX desk gamit ang MT4 demo account code + token

FILES
-----
Experts/JM_Forex_Bridge.mq4   — EA v2 (cloud + local file mode)
XM_MT4_SETUP.md               — Full step-by-step guide
SETUP-NO-AGENT.txt            — MT4 Real cloud setup (no PC agent)
SETUP-DEMO-LOCAL.txt          — MT4 Demo local file bridge
JM-FX-MT4-ACCOUNTS.txt        — Account codes + tokens

TROUBLESHOOTING
---------------
MT4 offline?     → AutoTrading ON? EA compiled v2.00?
Error 4060?      → Allow WebRequest URL sa MT4 Options
HTTP 403?        → Check InpBridgeToken
Wrong symbol?    → InpSymbol = exact broker gold symbol (GOLD / XAUUSD)
Real vs Demo?    → Real = cloud mode; Demo = local file bridge

SUPPORT
-------
Desk: https://jmtechsolution.cloud/fx/
