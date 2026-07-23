# JM Forex ↔ MT5 Auto Trade (Windows agent)

**No Python required** — uses PowerShell (built into Windows).

## Steps
1. Download: https://jmtechsolution.cloud/fx/downloads/jm-mt-agent.zip
2. Extract All
3. Open folder `jm-mt-agent` (config.json already filled)
4. Double-click **RUN_AGENT.bat** — keep the black window open
5. MT5: `JM_Forex_Bridge` on **XAUUSD**, Algo Trading ON, `UseCommonFolder=true`
6. Check: https://jmtechsolution.cloud/fx/api/mt/status → `"online": true`

## Notes
- Do **not** paste JSON into CMD / Win+R / browser docs pages
- If Windows blocks script: right-click `jm_mt_agent.ps1` → Properties → Unblock
