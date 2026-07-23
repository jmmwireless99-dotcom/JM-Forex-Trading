# JM Forex ↔ MT4 / MT5 Auto Trade (Windows agent)

**No Python required** — uses PowerShell (built into Windows).

Same agent works for **MT4** and **MT5**. Only one terminal should push at a time.

## Steps
1. Download: https://jmtechsolution.cloud/fx/downloads/jm-mt-agent.zip
2. Extract All
3. Open folder `jm-mt-agent` (config.json already filled)
4. Double-click **RUN_AGENT.bat** — keep the black window open
5. Attach the matching EA on **XAUUSD**, AutoTrading / Algo Trading ON, `UseCommonFolder=true`:
   - MT5 → https://jmtechsolution.cloud/fx/downloads/JM_Forex_Bridge.mq5
   - MT4 → https://jmtechsolution.cloud/fx/downloads/JM_Forex_Bridge.mq4
6. Check: https://jmtechsolution.cloud/fx/api/mt/status → `"online": true` and `mt_login` matches your account

## Notes
- Do **not** paste JSON into CMD / Win+R / browser docs pages
- If Windows blocks script: right-click `jm_mt_agent.ps1` → Properties → Unblock
- Common files folder is usually shared:  
  `%APPDATA%\MetaQuotes\Terminal\Common\Files`
- Server mode must match the terminal you run (`mt4` or `mt5`)
