# MT4 / MT5 integration + live candles

## Architecture

```
Dashboard (candles + controls)
        │
        ▼
JM Forex engine  ──paper──► simulated ticks / paper fills
        │
        └── mt4/mt5 ──file bridge──► JM_Forex_Bridge EA ──► Vantage account
```

## Install EA

### MT4
1. Copy `mt4/Experts/JM_Forex_Bridge.mq4` → `MQL4/Experts/`
2. Compile, attach to **XAUUSD** chart, AutoTrading ON
3. `UseCommonFolder = true`

### MT5
1. Copy `mt5/Experts/JM_Forex_Bridge.mq5` → `MQL5/Experts/`
2. Compile, attach to **XAUUSD** chart, Algo Trading ON
3. `UseCommonFolder = true`

Shared folder (both):
```
C:\Users\<YOU>\AppData\Roaming\MetaQuotes\Terminal\Common\Files
```

## Server env

```bash
# on the machine that can see the Common\Files folder
export JM_EXECUTION_MODE=mt4   # or mt5
export JM_MT4_BRIDGE_DIR="C:\\Users\\YOU\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files"
# or JM_MT5_BRIDGE_DIR=...
export JM_MT4_SYMBOL=XAUUSD
```

On the dashboard: choose **mt4** / **mt5** → **Apply mode**.

## Live candles

- Engine builds OHLC from ticks (`JM_CANDLE_PERIOD_SECONDS`, default **15**)
- Dashboard chart updates over WebSocket (`candle` / `candle_closed`)
- When MT bridge is online, candles follow real XAUUSD ticks from the EA

## Desk URL

https://jmtechsolution.cloud/fx/
