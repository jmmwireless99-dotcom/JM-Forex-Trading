# MT5 → JM FX (DDDC3D) — Walang PC Agent

Para sa **MT5 sa PC mo** + **JM FX cloud** (`jmtechsolution.cloud/fx/`) account **DDDC3D**.

Ang **EA v2** ang kumokonekta diretso sa cloud — hindi na kailangan ang `start-jm-mt5-agent.bat`.

```
JM FX Cloud (DDDC3D)  ←——HTTP——→  JM_Forex_Bridge EA  →  MT5 (GOLD#)
         ↑                                    ↑
   jmtechsolution.cloud/fx/          MT5 sa PC mo
```

---

## STEP 1 — Isara ang PC agent

Kung may bukas na **`start-jm-mt5-agent.bat`**:
1. Isara ang window
2. Huwag mo nang buksan habang naka-**Cloud Bridge** mode ka

---

## STEP 2 — I-download ang bagong EA v2

Browser:
```
https://jmtechsolution.cloud/fx/api/downloads/JM_Forex_Bridge.mq5
```

O buong pack:
```
https://jmtechsolution.cloud/fx/api/downloads/mt5-bridge.zip
```

---

## STEP 3 — I-install sa MT5

1. MT5 → **File → Open Data Folder**
2. Kopyahin ang `JM_Forex_Bridge.mq5` sa `MQL5\Experts\`
3. **MetaEditor → Compile (F7)** — dapat **0 errors**, version **2.00**

---

## STEP 4 — Payagan ang WebRequest sa MT5 (IMPORTANTE)

1. MT5 → **Tools → Options → Expert Advisors**
2. I-check ang **"Allow algorithmic trading"**
3. I-check ang **"Allow WebRequest for listed URL"**
4. Sa listahan, i-add:
   ```
   https://jmtechsolution.cloud
   ```
5. Click **OK**

Kung hindi mo gagawin ito, makikita sa Experts tab:
```
JM Bridge: allow WebRequest for https://jmtechsolution.cloud/fx/api
```

---

## STEP 5 — I-detach ang lumang EA, i-attach ang bago

1. Tanggalin ang lumang **JM_Forex_Bridge** sa GOLD# chart (kung naka-attach)
2. I-drag ulit ang **JM_Forex_Bridge** sa **GOLD# chart**
3. Sa inputs, i-set:

| Input | Value |
|-------|--------|
| `InpSymbol` | `GOLD#` |
| `InpUseCloudBridge` | **`true`** |
| `InpApiUrl` | `https://jmtechsolution.cloud/fx/api` |
| `InpBridgeToken` | `gTXmD7O-194jS9gveB1I5c9qjmNdqdUv` |
| `InpSyncEveryMs` | `400` |
| `UseCommonFolder` | `true` |
| `InpPollMs` | `100` |

4. **Algo Trading ON** (green)

---

## STEP 6 — Verify sa Experts tab

Dapat makita mo:
```
JM Forex MT5 Bridge v2 — CLOUD mode (no PC agent)
  API: https://jmtechsolution.cloud/fx/api
  Allow WebRequest for: ...
```

Walang error na `4060` o `HTTP error`.

---

## STEP 7 — Login sa JM FX cloud

1. Browser: **https://jmtechsolution.cloud/fx/**
2. Sign in:
   - Code: **`DDDC3D`**
   - Token: **`Wx5LEXzg8J8Bgok7Z3kTLEd6n2T0s3MI`**
3. Dapat sa dashboard:
   - **MT online** (green) within ~5 seconds
   - Balance mula sa MT5 (~$1000)
   - Gold tick nag-u-update

---

## STEP 8 — Test ping (optional)

Sa browser o PowerShell:
```powershell
curl -X POST "https://jmtechsolution.cloud/fx/api/mt/ping"
```

Dapat: `"ok": true` — ibig sabihin cloud ↔ EA ↔ MT5 OK.

---

## Flow (walang agent)

```
1. AI signal sa cloud → isulat ang order sa server bridge folder
2. EA GET /mt/remote/command  (~100ms poll)
3. EA execute sa MT5 (GOLD#)
4. EA POST /mt/remote/sync (status + ticks + ack)
5. Cloud makita ang fill → DDDC3D trade log updated
```

**Walang PC agent. Walang file sync sa internet.**

---

## Troubleshooting

| Problema | Solusyon |
|----------|----------|
| `allow WebRequest` error (4060) | Step 4 — i-add ang URL sa MT5 Options |
| MT offline sa dashboard | Algo Trading ON? EA v2 attached? Token tama? |
| HTTP 403 | Mali ang `InpBridgeToken` |
| Order reject | Market open? Lots ≥ 0.01? GOLD# symbol? |
| PC agent pa rin bukas | Isara — puwedeng mag-conflict |

---

## Quick checklist

```
[ ] PC agent — CLOSED
[ ] EA v2.00 compiled
[ ] WebRequest allowed for jmtechsolution.cloud
[ ] InpUseCloudBridge = true
[ ] InpBridgeToken = gTXmD7O-...
[ ] GOLD# chart + Algo Trading GREEN
[ ] Login DDDC3D sa jmtechsolution.cloud/fx/
[ ] Dashboard → MT online
```

---

## Local-only mode (alternative, walang cloud)

Kung gusto mo i-test **localhost** lang (hindi cloud desk):

1. EA: `InpUseCloudBridge = false`
2. Run JM FX backend sa PC (see docs/MT5_LOCAL_NO_AGENT.md)
3. Open `http://localhost:5173`

Pero para sa **DDDC3D sa cloud**, gamitin ang **Cloud Bridge = true** (steps above).
