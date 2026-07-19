# JM Forex Trading Platform Automation

Paper-trading automation desk for **JM Forex**: strategy signals → risk gates → simulated fills → live monitoring dashboard.

## What's included

| Layer | Role |
| --- | --- |
| **Trading engine** | Streams simulated FX ticks, runs the active strategy, routes approved orders |
| **Strategies** | `ema_crossover`, `rsi_mean_reversion` (pluggable registry) |
| **Risk manager** | Max positions, daily loss cap, per-trade risk %, default SL/TP |
| **Paper broker** | Instant market fills, mark-to-market, SL/TP exits |
| **API + WebSocket** | FastAPI REST control plane + live tick/account/position feed |
| **Dashboard** | JM Forex monitoring UI (start/stop engine, watch markets & positions) |

> This build is **paper mode only**. No live broker orders are placed.

## Quick start

```bash
# one-shot (API :8000 + UI :5173)
chmod +x scripts/dev.sh
./scripts/dev.sh
```

Or separately:

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

## API highlights

- `GET /api/health` — service check  
- `GET /api/status` — engine state  
- `POST /api/engine/start` / `POST /api/engine/stop`  
- `GET /api/strategies` · `POST /api/strategies/active`  
- `GET /api/account` · `/positions` · `/orders` · `/signals` · `/ticks`  
- `POST /api/orders` — manual paper order  
- `WS /api/ws` — live events (`tick`, `signal`, `account`, `positions`, …)

## Tests

```bash
cd backend
source .venv/bin/activate
pytest -q
```

## Project layout

```
backend/app/
  engine/       # orchestration loop
  strategies/   # signal generators
  risk/         # hard risk gates
  brokers/      # paper broker + market simulator
  api/          # REST + WebSocket
frontend/       # Vite + React dashboard
```

## Next steps (when you are ready)

1. Swap `MarketDataSimulator` for a real FX feed adapter  
2. Add a live broker adapter behind the same `PaperBroker` interface  
3. Persist trades/account history  
4. Add backtesting over historical candles  

## Config

Environment variables use the `JM_` prefix (see `backend/app/core/config.py`), e.g.:

```bash
export JM_INITIAL_BALANCE=10000
export JM_MAX_RISK_PER_TRADE_PCT=1.0
export JM_DEFAULT_SYMBOLS=EURUSD,GBPUSD,USDJPY,XAUUSD
```