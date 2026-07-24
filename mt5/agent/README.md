# JM Forex ↔ MT4 + MT5 (dual always-on)

Same PC can run **both** bridges at once:

| Account | Platform | Agent |
|---|---|---|
| JOEL MADERA `25817283` | MT5 only | `RUN_AGENT_MT5.bat` |
| Your own MT4 JM FX account | MT4 | `RUN_AGENT_MT4.bat` |

Files do not collide:
- MT5 EA → `jm_status.csv`, `jm_ticks.csv`, …
- MT4 EA → `jm4_status.csv`, `jm4_ticks.csv`, …

## Setup — MT5 only (Joel)
1. Download **bagong MT5 bridge**: https://jmtechsolution.cloud/fx/downloads/jm-mt5-bridge.zip  
2. Extract All → basahin `SETUP_MT5.txt`  
3. Compile/attach `JM_Forex_Bridge.mq5` on XAUUSD (Algo Trading ON, UseCommonFolder=true)  
4. Run `RUN_AGENT_MT5.bat` (keep open)  
5. Chart comment: `trade_ok=YES` · status: https://jmtechsolution.cloud/fx/api/mt/status  

## Setup — MT4 only (Nonoy)
1. Download **bagong MT4 bridge**: https://jmtechsolution.cloud/fx/downloads/jm-mt4-bridge.zip  
2. Extract All → basahin `SETUP_MT4.txt`  
3. Compile/attach `JM_Forex_Bridge.mq4` on XAUUSD (AutoTrading ON / GREEN, UseCommonFolder=true)  
4. Run `RUN_AGENT_MT4.bat` (keep open)  
5. Chart comment: `trade_ok=YES` · `platforms.mt4.online=true`

## Setup — dual MT4 + MT5
1. Download: https://jmtechsolution.cloud/fx/downloads/jm-mt-agent.zip  
2. Extract All  
3. **MT5:** compile/attach `JM_Forex_Bridge.mq5` on XAUUSD (Algo Trading ON)  
4. **MT4:** compile/attach `JM_Forex_Bridge.mq4` on XAUUSD (AutoTrading ON, UseCommonFolder=true)  
5. Start **both** agents (two windows):
   - `RUN_AGENT_MT5.bat`
   - `RUN_AGENT_MT4.bat`
6. Check: https://jmtechsolution.cloud/fx/api/mt/status  
   - `platforms.mt5.online` + `mt_login=25817283`  
   - `platforms.mt4.online` + your MT4 login  

## JM FX logins
- **Joel = MT5 only** — huwag i-link ang MT4 sa account ni Joel  
- **MT4:** gumawa ng **bagong** JM FX account → Link live → Platform **MT4** → MT4 login/password  

Paper demos stay paper. Only matching login binds to each terminal.
