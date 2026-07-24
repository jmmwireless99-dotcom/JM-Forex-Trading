# JM Forex ↔ MT4 + MT5 (dual always-on)

Same PC can run **both** bridges at once:

| Account | Platform | Agent |
|---|---|---|
| Joel `25817283` | MT5 | `RUN_AGENT_MT5.bat` |
| Your MT4 login | MT4 | `RUN_AGENT_MT4.bat` |

Files do not collide:
- MT5 EA → `jm_status.csv`, `jm_ticks.csv`, …
- MT4 EA → `jm4_status.csv`, `jm4_ticks.csv`, …

## Setup
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
- Joel MT5: username = MT5 account, password = MT5 password  
- MT4 account: Create account → Link live MT4/MT5 → choose **MT4**, enter MT4 login/password  

Paper demos stay paper. Only matching login binds to each terminal.
