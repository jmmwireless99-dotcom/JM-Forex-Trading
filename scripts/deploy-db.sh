#!/usr/bin/env bash
# Deploy Postgres + migrate on VPS (or local). Run from repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DB_URL="${JM_DATABASE_URL:-postgresql+psycopg://jm:jm_scalp_2026@127.0.0.1:5432/jm_forex}"
export JM_DATABASE_URL="$DB_URL"

echo "==> Starting Postgres (docker compose)"
docker compose up -d postgres

echo "==> Waiting for Postgres"
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U jm -d jm_forex >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> Installing Python DB deps"
cd "$ROOT/backend"
if [[ -x .venv/bin/pip ]]; then
  PIP=.venv/bin/pip
  PY=.venv/bin/python
  ALEMBIC=.venv/bin/alembic
else
  PIP=pip3
  PY=python3
  ALEMBIC=alembic
fi
$PIP install -q -r requirements.txt

echo "==> Alembic upgrade head"
$ALEMBIC upgrade head

echo "==> Seed strategies"
$PY -c "from app.db.seed import seed_strategies; print(seed_strategies(force_update=True))"

echo "==> Done. JM_DATABASE_URL=$JM_DATABASE_URL"
