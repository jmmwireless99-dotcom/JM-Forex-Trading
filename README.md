# JM Forex — Gold (XAUUSD) Automation

Paper-trading automation desk focused on **Gold vs USD (XAUUSD)**.

## Best strategy for us (recommended)

**`gold_confluence`** — session + news + indicator confluence.

| Layer | Rule | Why for gold |
| --- | --- | --- |
| **Session** | Trade London/NY (`07–20 UTC`), prefer **overlap `13–16 UTC`** | Best liquidity; Asia = fake breaks |
| **News** | Blackout **45m before / 30m after** NFP, CPI, FOMC-style USD prints | Gold spikes on USD data — automation should stand aside |
| **Trend** | EMA **21 / 55** | Direction filter |
| **Strength** | ADX **14 ≥ 22** | Skip chop |
| **Pullback** | RSI **14** in value zone (buy 40–55 / sell 45–60) + reclaim EMA21 | Don’t chase stretched gold |
| **Risk** | ATR **1.8× SL / 2.7× TP**, **0.5%/trade**, **1 position**, **2% daily loss** | Volatility-adaptive |

### Session map (UTC)

- **PRIME:** 13:00–16:00 — London/NY overlap  
- **ALLOWED:** 07:00–13:00 London · 16:00–20:00 NY  
- **AVOID:** Asia / weekend  

### News we respect

- NFP (first Friday)  
- CPI window  
- FOMC decision window  
- Core PCE window  

Enable live gates:

```bash
export JM_SESSION_FILTER=true
export JM_NEWS_FILTER=true
export JM_PRIME_SESSION_ONLY=false   # true = overlap only
export JM_DEFAULT_STRATEGY=gold_confluence
```

Secondary strategies (`gold_atr_trend`, `ema_crossover`, `rsi_mean_reversion`) stay available for comparison — **desk default is `gold_confluence`**.

## Quick start

```bash
chmod +x scripts/dev.sh
./scripts/dev.sh
```

- API: http://localhost:8000  
- Dashboard: http://localhost:5173  
- Desk filters: `GET /api/desk`

## AI & Machine Learning

The desk uses **AI & Machine Learning** (scikit-learn) to learn from your trade
history and score new setups — no hand-rule overrides on the probability.

- Online: `SGDClassifier(log_loss)` updates on every closed trade
- Batch retrain: `LogisticRegression` on full labeled history
- Storage: `data/ai_trade_history.jsonl` + `data/ai_trade_model.json`
- `GET /api/ai/advice` — TAKE / CAUTION / SKIP + ML win probability
- `GET /api/ai/history` — labeled feature history
- `POST /api/ai/retrain` — backfill journal + Machine Learning retrain
- `JM_AI_GATE_ENTRIES=true` → high-confidence **SKIP** blocks entry (`AI_SKIP`)

```bash
export JM_AI_ASSIST=true
export JM_AI_GATE_ENTRIES=true
export JM_AI_MIN_WIN_PROB=0.40
```

## Tests

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Layout

```
backend/app/strategies/
  gold_confluence.py   # recommended stack
  session.py           # London / NY / prime
  news_calendar.py     # USD news blackout
  indicators.py        # EMA, ATR, RSI, ADX
  gold_atr_trend.py    # simpler ATR fallback
```

## Deploy on jmtechsolution.cloud VPS

```bash
# on VPS after DNS: forex → VPS IP
./scripts/deploy-vps.sh
# then enable Apache site in deploy/apache-forex.jmtechsolution.cloud.conf
```

- Desk: `https://forex.jmtechsolution.cloud`  
- Portal button snippet: `deploy/portal-forex-button.snippet.js`  
- Full guide: **[docs/VPS_DEPLOY_JMTECH.md](docs/VPS_DEPLOY_JMTECH.md)**

## Connect MT4 (real demo execution)

MT4 has no native Python API — we use a **file bridge**:

1. Install `mt4/Experts/JM_Forex_Bridge.mq4` on your MT4 terminal  
2. Attach it to XAUUSD chart (AutoTrading ON)  
3. Point Python at the shared folder:

```bash
export JM_EXECUTION_MODE=mt4
export JM_MT4_BRIDGE_DIR="C:\\Users\\YOU\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files"
```

Full guide: **[docs/MT4_SETUP.md](docs/MT4_SETUP.md)**  
Status: `GET /api/mt4/status` · Ping: `POST /api/mt4/ping`

> Default remains **paper mode** until `JM_MT4_BRIDGE_DIR` is set.
