# XM MT4 Bridge Setup — JM FX

## MT4 Real (Cloud — no PC agent)

1. Download **JM-FX-MT4-Bridge-Pack.zip** or **mt4-real-ea-v2.zip**
2. Copy `Experts/JM_Forex_Bridge.mq4` → MT4 `MQL4/Experts/`
3. MetaEditor → Compile (F7) → version 2.00, 0 errors
4. MT4 → Tools → Options → Expert Advisors:
   - Allow automated trading
   - Allow WebRequest: `https://jmtechsolution.cloud`
5. Attach EA on **XAUUSD** (or broker gold symbol) on **REAL** terminal:
   - `InpSymbol` = broker gold symbol
   - `InpUseCloudBridge` = **true**
   - `InpBridgeToken` = from server admin
6. Login at https://jmtechsolution.cloud/fx/ with MT4 **real** account code
7. Verify: `/fx/api/mt4/real/status` → `"online": true`

## MT4 Demo (Local file bridge)

1. Same EA install as above
2. Attach on **GOLD** chart (XM demo):
   - `InpUseCloudBridge` = **false**
   - `UseCommonFolder` = **true**
3. Server must have `JM_MT4_BRIDGE_DIR` pointing to MT4 Common\Files
4. Login with MT4 **demo** account code on JM FX desk

## Broker symbols

| Broker | Demo | Real |
|--------|------|------|
| XM MT4 | GOLD | XAUUSD |

Set `InpSymbol` to the exact symbol shown in Market Watch.
