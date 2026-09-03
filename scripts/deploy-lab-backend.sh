#!/usr/bin/env bash
# Install/restart JM Lab trading API (port 8001). Does NOT touch jm-forex.service.
#
# On VPS:
#   cd /opt/jm-lab-src && ./scripts/deploy-lab-backend.sh
#   (isolated worktree — see scripts/remote-deploy-lab.sh, does not share a
#   checkout with /opt/jm-forex-trading, which runs jm-forex.service)
#
# Optional env:
#   BRANCH=cursor/lab-demo-trading-c11c   (default: main)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${BRANCH:-main}"
LAB_DIR="$ROOT/lab-backend"
UNIT_SRC="$ROOT/deploy/jm-lab.service"
UNIT="/etc/systemd/system/jm-lab.service"

if [[ "${SKIP_GIT_FETCH:-}" != "1" ]]; then
  echo "[1/4] Fetch lab-backend sources (${BRANCH})..."
  git fetch origin "${BRANCH}"
  git checkout -B "${BRANCH}" "origin/${BRANCH}"
else
  echo "[1/4] Skip git fetch (SKIP_GIT_FETCH=1)..."
fi

if [[ ! -f "$LAB_DIR/requirements.txt" ]]; then
  echo "ERROR: lab-backend/ not found on branch ${BRANCH}"
  exit 1
fi

echo "[2/4] Python venv + deps..."
cd "$LAB_DIR"
if [[ ! -x .venv/bin/pip ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

mkdir -p data
touch data/.gitkeep

echo "[3/4] systemd jm-lab.service..."
if [[ ! -f "$UNIT_SRC" ]]; then
  echo "ERROR: missing $UNIT_SRC"
  exit 1
fi
sudo cp "$UNIT_SRC" "$UNIT"
sudo systemctl daemon-reload
sudo systemctl enable jm-lab.service

echo "[4/4] Restart jm-lab..."
sudo systemctl restart jm-lab.service
sleep 2
sudo systemctl is-active jm-lab.service
curl -fsS http://127.0.0.1:8001/api/health
echo
echo "OK — JM Lab API on :8001 (jm-forex.service unchanged)"
