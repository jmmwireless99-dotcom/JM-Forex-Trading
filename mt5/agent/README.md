# JM Forex ↔ MT5 Auto Trade (Windows agent)

## Requirements
- Vantage MT5 logged in (demo OK)
- `JM_Forex_Bridge` EA on **XAUUSD** chart (`UseCommonFolder=true`, Algo Trading ON)
- Python 3.10+ on the same Windows PC

## Steps
1. Download EA: https://jmtechsolution.cloud/fx/downloads/JM_Forex_Bridge.mq5
2. Download agent zip: https://jmtechsolution.cloud/fx/downloads/jm-mt-agent.zip
3. Unzip → copy `config.example.json` to `config.json`
4. Put the bridge token in `config.json` → `bridge_token`
5. Leave `files_dir` empty (auto: `%APPDATA%\MetaQuotes\Terminal\Common\Files`)
6. Double-click **RUN_AGENT.bat** — keep it open
7. On FX desk: mode **mt5** → Apply mode

## Check
```
https://jmtechsolution.cloud/fx/api/mt/status
```
Wanted: `"online": true`, `"remote_bridge": true`

## Notes
- Cloud desk (Linux) cannot see your Windows folder — this agent is the link.
- Logout / close agent = MT offline (desk falls back / rejects MT orders).
- Never commit `config.json` with a real token.
