# Proxmox — Windows VM All-in-One (jmtechsolution.cloud + MT5)

**Isang Windows VM lang** sa Proxmox: JM FX desk + MT5 + DDDC3D — **walang PC agent**, **walang Linux VM**.

```
Proxmox
└── Windows Server VM
    ├── MetaTrader 5 (XM Demo 169250320)
    ├── JM_Forex_Bridge EA (local file mode)
    ├── JM FX Backend (Python :8000)
    ├── Caddy (HTTPS jmtechsolution.cloud/fx/)
    └── DDDC3D auto-trading + matched trade logs
```

---

## PART 1 — Proxmox: gumawa ng Windows VM

### Specs (minimum)

| Resource | Value |
|----------|--------|
| OS | Windows Server 2019/2022 **or** Windows 10/11 Pro |
| vCPU | 4 |
| RAM | 8 GB (4 GB minimum) |
| Disk | 80 GB SSD |
| Network | Bridge (vmbr0), public IP o port-forward |

### Steps sa Proxmox UI

1. **Download Windows Server ISO** → upload sa Proxmox storage
2. **Create VM** → ISO boot → install Windows
3. Install **VirtIO drivers** (network + disk) kung QEMU/KVM
4. Enable **Auto Start** sa VM Options
5. Sa router/firewall: forward **80 + 443** → Windows VM IP (para sa HTTPS)

---

## PART 2 — Windows VM: install prerequisites

Buksan **PowerShell as Administrator**:

```powershell
# Git, Python 3.11, Node.js LTS
winget install Git.Git
winget install Python.Python.3.11
winget install OpenJS.NodeJS.LTS

# Caddy (HTTPS reverse proxy — mas simple kaysa IIS)
winget install Caddy.Caddy

# NSSM (Windows service para sa JM FX backend)
winget install NSSM.NSSM
```

**I-restart ang VM** pagkatapos.

---

## PART 3 — Clone JM FX repo

```powershell
cd C:\
git clone https://github.com/jmmwireless99-dotcom/JM-Forex-Trading.git jm-forex-trading
cd jm-forex-trading
git checkout cursor/dddc3d-mt5-logs-c11c
```

---

## PART 4 — Automated setup script

```powershell
cd C:\jm-forex-trading
powershell -ExecutionPolicy Bypass -File .\scripts\windows\setup-jmfx-allinone.ps1
```

Gagawin ng script:
- Python venv + pip install
- Build frontend (`JM_BASE=/fx/`)
- Gumawa ng `.env` para sa local MT5 bridge
- DDDC3D account create

---

## PART 5 — XM MetaTrader 5

1. Download: https://www.xm.com/mt5
2. Login demo: **169250320**
3. Symbol: **GOLD#** sa chart
4. Copy `mt5\Experts\JM_Forex_Bridge.mq5` → `MQL5\Experts\`
5. Compile (F7) — version **2.00**
6. Attach EA sa GOLD# chart:

| Input | Value |
|-------|--------|
| `InpSymbol` | `GOLD#` |
| **`InpUseCloudBridge`** | **`false`** ← local mode |
| `UseCommonFolder` | `true` |
| Algo Trading | **GREEN** |

**Hindi kailangan ang WebRequest** sa all-in-one local mode.

---

## PART 6 — `.env` (local bridge — key settings)

File: `C:\jm-forex-trading\.env`

```ini
JM_EXECUTION_MODE=paper
JM_MT5_BRIDGE_DIR=C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\Common\Files
JM_MT_SYMBOL=GOLD#
JM_MT5_DEMO_ACCOUNT_CODE=DDDC3D
JM_MT5_DEMO_LOGIN=169250320
JM_MT_REMOTE_BRIDGE=false

JM_DEFAULT_STRATEGY=AI_ML
JM_AUTO_STRATEGY=true
JM_AI_ASSIST=true
JM_AI_GATE_ENTRIES=true
JM_ASIA_DESK_ONLY=true
JM_AUTO_FILL_SINGLE_BOOK=false
JM_STATIC_DIR=C:\jm-forex-trading\backend\static
JM_PORTAL_URL=https://jmtechsolution.cloud
```

Palitan `Administrator` → Windows username mo.

---

## PART 7 — Start JM FX as Windows Service

```powershell
cd C:\jm-forex-trading
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-jmfx-service.ps1
```

Test:
```powershell
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/mt/status
```

Dapat: `"online": true`

---

## PART 8 — HTTPS: jmtechsolution.cloud

### DNS

Sa domain panel, i-point ang **A record**:

| Type | Name | Value |
|------|------|-------|
| A | `@` | `<Windows VM public IP>` |
| A | `www` | `<Windows VM public IP>` |

### Caddy (HTTPS + /fx/ proxy)

1. Copy config:
   ```powershell
   copy C:\jm-forex-trading\deploy\Caddyfile.windows C:\Caddy\Caddyfile
   ```
2. Edit `C:\Caddy\Caddyfile` — palitan ang email sa `tls` block
3. Start Caddy:
   ```powershell
   caddy run --config C:\Caddy\Caddyfile
   ```
4. Para auto-start, install Caddy as service (winget service o NSSM)

### Test

```
https://jmtechsolution.cloud/fx/
https://jmtechsolution.cloud/fx/api/mt/status
https://jmtechsolution.cloud/fx/api/health
```

---

## PART 9 — Login DDDC3D

| Field | Value |
|-------|--------|
| URL | https://jmtechsolution.cloud/fx/ |
| Code | `DDDC3D` |
| Token | *(from setup script output)* |

Dapat: **MT online**, balance from MT5, trade logs match MT5 fills.

---

## PART 10 — Auto-start checklist (24/7)

| Item | How |
|------|-----|
| Proxmox VM | Options → Start at boot |
| Windows | Disable sleep/hibernate |
| MT5 | Task Scheduler → run at logon |
| EA | Re-attach after MT5 start (or save chart template) |
| JM FX service | NSSM → auto start |
| Caddy | Windows service |

---

## Migrate from old Linux VPS

1. Setup Windows VM (steps above) at **test** first
2. Verify MT online + trades on Windows
3. Change DNS A record → Windows VM IP (TTL 300)
4. Stop old Linux jm-forex service after DNS propagates
5. Keep Linux VM snapshot as backup 1 week

---

## Troubleshooting

| Problema | Fix |
|----------|-----|
| MT offline | MT5 open, EA attached, Algo ON, check `JM_MT5_BRIDGE_DIR` path |
| 502 on /fx/ | JM FX service running? `curl localhost:8000/api/health` |
| SSL error | Caddy running, port 443 open sa firewall |
| Wrong bridge path | Copy exact Common\Files path from File Explorer |

---

## Quick checklist

```
[ ] Proxmox Windows VM created (4 CPU, 8GB RAM)
[ ] Python + Node + Git + Caddy installed
[ ] setup-jmfx-allinone.ps1 completed
[ ] MT5 + EA v2 local mode (InpUseCloudBridge=false)
[ ] JM FX service running (:8000)
[ ] DNS → Windows VM IP
[ ] Caddy HTTPS working
[ ] https://jmtechsolution.cloud/fx/ → MT online
[ ] DDDC3D login OK
```
