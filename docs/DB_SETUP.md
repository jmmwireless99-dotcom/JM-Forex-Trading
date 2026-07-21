# JM Forex — Postgres setup & VPS deploy

## Review of Gemini draft

Kept as-is (good):
- `strategies` with JSONB parameters
- `market_data_candles` OHLCV
- `liquidity_zones_and_fvgs` for SMC
- `signals` → `trades` FK flow
- status enums for signal/trade lifecycle

Hardened for production:
- UNIQUE `(symbol, timeframe, timestamp)` on candles
- UNIQUE `strategies.name`
- Extra zone types: `PDH`, `PDL`, `ORDER_BLOCK`
- `timeframe` on signals; `strategy_id` + `ticket` + `mode` on trades
- `is_mitigated` for FVG/OB lifecycle
- Gold-friendly `NUMERIC(14,5)` + indexes on symbol/status/time

Stack: **PostgreSQL 16 + SQLAlchemy 2 + Alembic** (matches existing Python FastAPI desk).

---

## Local / Docker

```bash
# 1) Start Postgres (+ optional app container)
docker compose up -d postgres

# 2) Wait healthy, then migrate + seed
cd backend
export JM_DATABASE_URL='postgresql+psycopg://jm:jm_scalp_2026@127.0.0.1:5432/jm_forex'
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -c 'from app.db.seed import seed_strategies; print(seed_strategies())'

# 3) Or apply raw DDL once (init volume also mounts db/schema.sql)
# psql "$JM_DATABASE_URL" -f ../db/schema.sql
```

App env:
```
JM_DATABASE_URL=postgresql+psycopg://jm:jm_scalp_2026@127.0.0.1:5432/jm_forex
JM_DATABASE_AUTO_MIGRATE=true
JM_DATABASE_SEED_ON_BOOT=true
```

API checks:
- `GET /api/db/health`
- `GET /api/db/strategies`

---

## VPS (systemd desk + Docker Postgres)

Typical layout on `72.62.73.235`:
- App: `/opt/jm-forex-trading` + `jm-forex.service`
- DB: Docker container `jm-forex-db` on `127.0.0.1:5432`

```bash
cd /opt/jm-forex-trading
git pull
docker compose up -d postgres

# systemd Environment=
# JM_DATABASE_URL=postgresql+psycopg://jm:jm_scalp_2026@127.0.0.1:5432/jm_forex
# JM_DATABASE_AUTO_MIGRATE=true
# JM_DATABASE_SEED_ON_BOOT=true

cd backend
.venv/bin/pip install -r requirements.txt
JM_DATABASE_URL=... .venv/bin/alembic upgrade head
systemctl restart jm-forex.service
curl -s http://127.0.0.1:8000/api/db/health
curl -s http://127.0.0.1:8000/api/db/strategies
```

Change `POSTGRES_PASSWORD` / URL before public exposure; keep port bound to localhost when possible.
