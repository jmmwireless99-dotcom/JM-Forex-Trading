# Paano i-connect ang MT4 sa JM Forex AI

MT4 **walang official Python API**. Kaya gumagamit tayo ng **file bridge**:

```
JM Forex AI (Python)
        │  writes jm_command.csv
        ▼
MT4 Common\Files  ◄── shared folder
        ▲
        │  JM_Forex_Bridge.mq4 reads command → OrderSend()
        │  writes jm_status / jm_ticks / jm_ack
```

**Python AI = utak (strategy + risk).**  
**MT4 EA = kamay (execute sa broker).**

---

## Step 1 — Maghanda ng MT4 (ikaw)

1. Mag-install ng MT4 mula sa broker mo  
2. Mag-login sa **DEMO** account muna  
3. Buksan ang chart ng **XAUUSD** (o `GOLD` — depende sa broker symbol)  
4. I-enable: **AutoTrading** (toolbar) + **Allow live trading** sa EA settings  

---

## Step 2 — I-install ang JM Bridge EA

1. Sa MT4: `File → Open Data Folder`  
2. Punta sa `MQL4/Experts/`  
3. Kopyahin ang file mula sa repo:
   - `mt4/Experts/JM_Forex_Bridge.mq4`
4. Buksan sa **MetaEditor** → **Compile** (F7) — dapat walang error  
5. I-drag ang `JM_Forex_Bridge` sa **XAUUSD** chart  
6. Inputs:
   - `InpSymbol` = exact symbol sa broker (`XAUUSD` o `GOLD` o `XAUUSDm`)  
   - `UseCommonFolder` = `true`  
7. OK → dapat may smiley face sa chart + AutoTrading ON  

---

## Step 3 — Hanapin ang shared folder

Kapag `UseCommonFolder=true`:

```
C:\Users\<YOUR_USER>\AppData\Roaming\MetaQuotes\Terminal\Common\Files
```

Dito lalabas ang:
- `jm_status.csv`
- `jm_ticks.csv`
- `jm_positions.csv`
- `jm_command.csv` (sinusulat ng AI)
- `jm_ack.csv`

---

## Step 4 — I-connect ang Python AI

Sa machine kung saan tumatakbo ang JM Forex backend:

```bash
# Windows path example
export JM_EXECUTION_MODE=mt4
export JM_MT4_BRIDGE_DIR="C:\\Users\\YOU\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files"
export JM_MT4_SYMBOL=XAUUSD
export JM_DEFAULT_STRATEGY=gold_confluence
export JM_SESSION_FILTER=true
export JM_NEWS_FILTER=true

./scripts/dev.sh
```

Check:

```bash
curl http://localhost:8000/api/mt4/status
curl -X POST http://localhost:8000/api/mt4/ping
```

`online: true` + ping `ok: true` = connected na.

---

## Step 5 — Flow kapag connected

1. AI (`gold_confluence`) gumagawa ng signal  
2. Risk manager mag-a-approve/reject  
3. Bridge magsusulat ng `OPEN` command  
4. MT4 EA magpo-`OrderSend` sa broker  
5. Status/positions babalik sa AI dashboard  

---

## Important

| Rule | Detail |
| --- | --- |
| Demo muna | Huwag live hanggang stable ang ping + 1–2 weeks demo |
| Symbol name | Dapat tumugma ang `InpSymbol` sa broker (XAUUSD vs GOLD) |
| MT4 dapat naka-open | File bridge gumagana lang habang naka-run ang terminal + EA |
| Same PC / synced folder | Python kailangan makita ang `Common\Files` path |
| Paper default | Kung walang `JM_MT4_BRIDGE_DIR`, paper mode pa rin |

---

## Troubleshooting

| Problema | Fix |
| --- | --- |
| `online: false` | EA ba naka-attach? AutoTrading ON? Tama ba ang folder path? |
| ping timeout | Compile EA ulit; check Experts tab for errors |
| Order rejected | Market closed? Symbol wrong? Lots too small/large for broker? |
| Walang file | `UseCommonFolder=true` at tingnan Common\\Files hindi Terminal\\Files |

---

## Next (optional)

- Sync folder via network share kung AI tumatakbo sa ibang PC/VPS  
- MT5 Python package later (mas direkta kaysa MT4)  
- I-wire ang engine `execution_mode=mt4` para auto-send approved signals (demo first)
