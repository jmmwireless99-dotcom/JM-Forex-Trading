#!/usr/bin/env bash
# Rebuild frontend for https://jmtechsolution.cloud/fx/ and restart systemd service.
# Usage on VPS: cd /opt/jm-forex-trading && ./scripts/deploy-fx-portal.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[1/4] Pull latest..."
git pull --ff-only || true

echo "[2/4] Build frontend with base=/fx/ ..."
cd "$ROOT/frontend"
npm ci --silent
JM_BASE=/fx/ npm run build

echo "[3/4] Publish static assets..."
rm -rf "$ROOT/backend/static"
mkdir -p "$ROOT/backend/static"
cp -a "$ROOT/frontend/dist/." "$ROOT/backend/static/"

# Sanity: asset paths must be under /fx/
if ! grep -q '/fx/assets/' "$ROOT/backend/static/index.html"; then
  echo "ERROR: index.html missing /fx/assets/ base — refusing deploy"
  grep -E 'src=|href=' "$ROOT/backend/static/index.html" || true
  exit 1
fi

echo "[4/4] Restart jm-forex..."
systemctl restart jm-forex.service
sleep 2
systemctl is-active jm-forex.service
curl -fsS http://127.0.0.1:8000/api/health
echo
echo "OK — open https://jmtechsolution.cloud/fx/"
