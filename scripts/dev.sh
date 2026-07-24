#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$ROOT/backend/.venv" ]]; then
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  (cd "$ROOT/frontend" && npm install)
fi

echo "Starting JM Forex API on :8000 and dashboard on :5173"
trap 'kill 0' EXIT
(
  cd "$ROOT/backend"
  .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
) &
(
  cd "$ROOT/frontend"
  npm run dev -- --host 0.0.0.0 --port 5173
) &
wait