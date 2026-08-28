# XM MT5 Demo → JM FX Setup (Step-by-step)

Ito ang buong guide para i-connect ang **XM MetaTrader 5 demo** sa **JM FX desk**.

> **Important:** Ang XM login/password ay ilalagay sa **MT5 terminal lang** — hindi sa JM FX website o GitHub.

---

## Files na kailangan mo (mula sa repo)

| File | Copy to |
|------|---------|
| `mt5/Experts/JM_Forex_Bridge.mq5` | `MQL5/Experts/JM_Forex_Bridge.mq5` |
| `scripts/create_xm_mt5_demo_account.py` | (sa server — para sa dedicated JM account) |
| `.env.mt5.xm.example` | i-rename to `.env` at i-edit ang paths |

---

## PART A — XM MT5 sa Windows PC

### Step 1 — Download at install MT5 (XM)

1. Buksan: https://www.xm.com/mt5  
2. I-download ang **MetaTrader 5 for XM**  
3. I-install at buksan ang MT5  

### Step 2 — Login sa XM Demo

1. **File → Login to Trade Account**  
2. Ilagay ang credentials mula sa **XM welcome email**:
   - **Login:** `169250320`  
   - **Password:** ilagay sa MT5 terminal lang (hindi sa JM FX cloud)  
   - **Server:** hal. `XMGlobal-MT5 5` / `XM.com-Demo` (exact name sa email)  
3. Dapat connected (green bars sa ibaba)  

> Kung hindi makalogin: i-reset ang demo password sa XM Members Area.

### Step 3 — Hanapin ang Gold symbol sa XM

1. **View → Market Watch** (Ctrl+M)  
2. Right-click → **Symbols** → hanapin ang gold  
3. Karaniwang pangalan sa XM:
   - `GOLD#` ← **gamitin ito** (XM MT5 demo account 169250320)
   - `GOLD` / `GOLD24-7#`
   - `XAUUSD` / `XAUUSD#`
4. I-drag sa chart at **tandaan ang exact name**  

### Step 4 — Install JM Bridge EA

1. Sa MT5: **File → Open Data Folder**  
2. Punta sa folder: `MQL5/Experts/`  
3. Kopyahin ang `mt5/Experts/JM_Forex_Bridge.mq5` mula sa repo  
4. Sa MT5: **Navigator → Expert Advisors** → right-click → **Refresh**  
5. Buksan sa **MetaEditor** → **Compile** (F7) — dapat **0 errors**  

### Step 5 — Attach EA sa chart

1. I-drag ang **JM_Forex_Bridge** sa **gold chart**  
2. Sa inputs:
   - `InpSymbol` = **exact XM symbol** (hal. `GOLD`)  
   - `UseCommonFolder` = **true**  
   - `InpMagic` = `260719` (default OK)  
3. **Algo Trading ON** (green button sa toolbar)  
4. Dapat may smiley sa chart  

### Step 6 — Verify bridge files

Buksan ang folder (Windows):

```
C:\Users\<YOUR_USER>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\
```

Dapat may files na:
- `jm_status.csv`  
- `jm_ticks.csv`  
- `jm_positions.csv`  

Kung wala: check `UseCommonFolder=true` at naka-ON ang Algo Trading.

---

## PART B — Dedicated JM FX account (XM MT5 Demo)

Gumagawa ng **hiwalay na JM FX account** para sa trade log at dashboard mo.

### JM FX account (already created)

| Field | Value |
|-------|--------|
| **Account code** | `DDDC3D` |
| **MT5 login** | `169250320` |
| **Label** | XM MT5 Demo · Login 169250320 |

Sa dashboard: **Sign in** gamit ang account code + token (hindi ang MT5 password).

### `.env` settings (sa server — remote bridge):

```bash
JM_EXECUTION_MODE=mt5
JM_MT5_BRIDGE_DIR=C:\Users\YOUR_USER\AppData\Roaming\MetaQuotes\Terminal\Common\Files
JM_MT_SYMBOL=GOLD
JM_MT5_DEMO_ACCOUNT_CODE=XXXXXX

JM_DEFAULT_STRATEGY=AI_ML
JM_AUTO_STRATEGY=true
JM_AI_ASSIST=true
JM_AI_GATE_ENTRIES=true
```

Palitan:
- `YOUR_USER` → Windows username  
- `GOLD` → exact XM symbol  
- `XXXXXX` → account code mula sa create script  

### Restart JM FX service

```bash
sudo systemctl restart jm-forex
```

### Sa dashboard

1. Piliin **mt5** sa dropdown  
2. Click **Apply mode**  
3. Dapat: **MT online** (green)  

### Test connection

```bash
curl https://jmtechsolution.cloud/fx/api/mt/status
curl -X POST https://jmtechsolution.cloud/fx/api/mt/ping
```

Dapat `"online": true` at ping `"OK"`.

---

## PART D — PC Bridge Agent (Cloud setup — walang Syncthing)

Kung ang JM FX ay nasa **Linux cloud** at ang MT5 ay nasa **Windows PC** mo, gamitin ang **PC Agent**:

### Sa cloud (agent / server — automatic)

```bash
cd /opt/jm-forex-trading
chmod +x scripts/setup_mt5_remote_bridge.sh
JM_MT5_DEMO_ACCOUNT_CODE=DDDC3D JM_MT_SYMBOL=GOLD24-7# ./scripts/setup_mt5_remote_bridge.sh
```

### Sa Windows PC mo (isang beses)

1. I-download mula sa repo:
   - `scripts/jm_mt5_pc_agent.py`
   - `scripts/start-jm-mt5-agent.bat`
2. MT5 bukas + **JM_Forex_Bridge** attached + **Algo Trading ON**
3. Double-click **`start-jm-mt5-agent.bat`**
4. Huwag isara ang window — sync every 0.5s papunta sa cloud

Dapat sa desk: **MT online** (green).

Token default: same as server `JM_MT_BRIDGE_TOKEN` (sa agent script).

---

## Flow kapag connected

```
AI_ML signal → Risk check → jm_command.csv → MT5 EA → XM Demo order
                     ↑                              ↓
              JM FX trade log              jm_ticks / jm_status
```

---

## Troubleshooting

| Problema | Solusyon |
|----------|----------|
| `online: false` | MT5 open ba? EA attached? Algo Trading ON? |
| ping timeout | Compile ulit ang EA; check Experts tab |
| Order rejected | Mali symbol? Market closed? Lots too small? |
| Wrong symbol | `InpSymbol` at `JM_MT_SYMBOL` dapat pareho sa XM |
| Cloud server offline | Kailangan MT5 sa Windows — hindi pwede Linux-only |

---

## Security

- **Demo muna** — huwag live hanggang stable ang ping + 1–2 weeks  
- **Huwag i-commit** ang `.env`, password, o account token sa GitHub  
- **Palitan** ang password kung na-share na sa chat/email  

---

## Quick checklist

- [ ] XM MT5 installed + demo logged in  
- [ ] Gold symbol identified (`GOLD` / `XAUUSD`)  
- [ ] `JM_Forex_Bridge.mq5` compiled + attached  
- [ ] Algo Trading ON  
- [ ] `jm_status.csv` updating sa Common\Files  
- [ ] JM FX account created (`create_xm_mt5_demo_account.py`)  
- [ ] `.env` may `JM_EXECUTION_MODE=mt5` + bridge path  
- [ ] Dashboard → mt5 → Apply mode → MT online  
