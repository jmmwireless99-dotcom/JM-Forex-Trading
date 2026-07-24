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

## VPS (systemd desk + Postgres)

On `72.62.73.235` the desk runs via systemd; Postgres is **apt PostgreSQL 16** on `127.0.0.1:5432`
(Docker Compose also works when port 5432 is free).

```bash
cd /opt/jm-forex-trading
git pull

# If using Docker (port 5432 free):
# docker compose up -d postgres

# Apt fallback (already used on live VPS):
# apt install postgresql postgresql-contrib
# createuser/db: jm / jm_forex

export JM_DATABASE_URL='postgresql+psycopg://jm:jm_scalp_2026@127.0.0.1:5432/jm_forex'
cd backend && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -c 'from app.db.seed import seed_strategies; print(seed_strategies())'

# systemd: JM_DATABASE_URL + AUTO_MIGRATE + SEED_ON_BOOT
systemctl restart jm-forex.service
curl -s http://127.0.0.1:8000/api/db/health
curl -s http://127.0.0.1:8000/api/db/strategies
```

Change the DB password before exposing anything beyond localhost.
