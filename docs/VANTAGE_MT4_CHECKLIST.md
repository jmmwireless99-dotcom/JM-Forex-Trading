# Vantage MT4 Demo — Joel checklist

Broker: **Vantage Markets** · Platform: **MT4** · Server: **VantageMarkets-Demo**

> Put login/password only inside your local MT4 terminal.  
> **Never** commit passwords to Git, `.env` in the repo, or chat screenshots you plan to keep public.

## 1) Login sa MT4 (sa Windows PC / laptop mo)

1. I-download/install ang **Vantage MT4** (mula sa Vantage client area / Trade button)
2. Open MT4 → `File` → `Login to Trade Account`
3. Enter:
   - **Login:** your demo account number  
   - **Password:** from Vantage email (Investor password is different — use the **main/trade** password)  
   - **Server:** `VantageMarkets-Demo`
4. Dapat connected (bottom-right: green / no “Invalid account”)

## 2) Hanapin ang Gold symbol

Sa Market Watch (`Ctrl+M`):

- Search: `XAUUSD` / `GOLD` / `XAUUSDm` (Vantage naming varies)
- Right-click → **Show** / **Show All** if missing
- Open a chart for that exact symbol name

Write down the **exact** symbol string — you will put it in the EA `InpSymbol`.

## 3) Install JM Forex Bridge EA

1. MT4 → `File` → `Open Data Folder`
2. Go to `MQL4/Experts/`
3. Copy from this repo: `mt4/Experts/JM_Forex_Bridge.mq4`
4. MetaEditor → Compile (F7)
5. Attach EA to the **gold chart**
6. Inputs:
   - `InpSymbol` = exact Vantage gold symbol  
   - `UseCommonFolder` = `true`  
   - `InpMagic` = `260719`
7. Check: **Allow live trading** + toolbar **AutoTrading** ON  
8. Smiley face on chart = EA running

## 4) Shared folder path (for Python AI)

Usually:

```
C:\Users\<YOUR_WINDOWS_USER>\AppData\Roaming\MetaQuotes\Terminal\Common\Files
```

After EA runs a few seconds you should see:

- `jm_status.csv`
- `jm_ticks.csv`
- `jm_positions.csv`

## 5) Point JM Forex AI to that folder

On the same PC (or a synced path), create a **local** `.env` (not committed):

```bash
JM_EXECUTION_MODE=mt4
JM_MT4_BRIDGE_DIR=C:\Users\YOUR_WINDOWS_USER\AppData\Roaming\MetaQuotes\Terminal\Common\Files
JM_MT4_SYMBOL=XAUUSD
JM_DEFAULT_STRATEGY=auto_gold
JM_AUTO_STRATEGY=true
JM_SESSION_FILTER=true
JM_NEWS_FILTER=true
JM_INITIAL_BALANCE=1000
```

Then:

```bash
./scripts/dev.sh
curl http://localhost:8000/api/mt4/status
curl -X POST http://localhost:8000/api/mt4/ping
```

Wanted result: `"online": true` and ping `"ok": true`.

## Account notes (your demo)

| Field | Value |
| --- | --- |
| Broker | Vantage Markets |
| Account | Demo · Standard STP |
| Server | VantageMarkets-Demo |
| Leverage | 500:1 |
| Balance | ~1000 USD |
| Risk tip | Keep automation at **0.5%/trade** — 500:1 leverage can wipe demo fast if lots are large |

Full bridge docs: [MT4_SETUP.md](./MT4_SETUP.md)
