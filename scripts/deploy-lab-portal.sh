#!/usr/bin/env bash
# Deploy JM Lab UI ONLY — does NOT rebuild JM FX, does NOT restart jm-forex.service.
#
# On VPS:
#   cd /opt/jm-forex-trading && ./scripts/deploy-lab-portal.sh
#
# Optional env:
#   BRANCH=cursor/experiment-lab-ui-c11c   (default: main)
#   JM_LAB_DIR=/opt/jm-lab/dist            (static output)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${BRANCH:-main}"
LAB_DIR="${JM_LAB_DIR:-/opt/jm-lab/dist}"

echo "[1/4] Fetch lab-ui sources (${BRANCH})..."
git fetch origin "${BRANCH}"
git checkout -B "${BRANCH}" "origin/${BRANCH}"

if [[ ! -d lab-ui ]]; then
  echo "ERROR: lab-ui/ not found on branch ${BRANCH}"
  exit 1
fi

echo "[2/4] Build lab-ui (base=/lab/)..."
cd "$ROOT/lab-ui"
if [[ -f package-lock.json ]]; then
  npm ci --silent
else
  npm install --silent
fi
JM_LAB_BASE=/lab/ npm run build

if [[ ! -f dist/index.html ]]; then
  echo "ERROR: lab-ui build failed — no dist/index.html"
  exit 1
fi

if ! grep -q '/lab/assets/' dist/index.html; then
  echo "ERROR: index.html missing /lab/assets/ base"
  grep -E 'src=|href=' dist/index.html || true
  exit 1
fi

echo "[3/4] Publish static files → ${LAB_DIR}..."
mkdir -p "$(dirname "$LAB_DIR")"
rm -rf "${LAB_DIR}"
mkdir -p "${LAB_DIR}"
cp -a dist/. "${LAB_DIR}/"
chown -R www-data:www-data "$(dirname "$LAB_DIR")" 2>/dev/null || true

echo "[4/5] Apache snippet (manual once if not yet installed)..."
SNIP="$ROOT/deploy/apache-lab-path.conf"
if [[ -f "$SNIP" ]]; then
  echo "  Include ${SNIP} in your SSL vhost if /lab/ is not configured yet."
  if [[ -d /etc/apache2/sites-available ]]; then
    if ! grep -rq 'jm-lab/dist' /etc/apache2/sites-enabled/ 2>/dev/null; then
      echo "  NOTE: Apache /lab/ alias not detected — run once on VPS:"
      echo "    sudo bash $ROOT/scripts/install-apache-lab-snippet.sh"
    else
      echo "  Apache /lab/ alias appears configured."
      if command -v apache2ctl >/dev/null 2>&1; then
        sudo apache2ctl configtest && sudo systemctl reload apache2
      fi
    fi
  fi
fi

if [[ -x "$ROOT/scripts/deploy-lab-backend.sh" && -d "$ROOT/lab-backend" ]]; then
  echo "[5/5] Lab demo trading API (port 8001)..."
  SKIP_GIT_FETCH=1 BRANCH="${BRANCH}" bash "$ROOT/scripts/deploy-lab-backend.sh"
else
  echo "[5/5] Skipped lab-backend (not on this branch yet)."
fi

echo ""
echo "OK — JM Lab static files deployed to ${LAB_DIR}"
echo "    JM FX (/fx/) was NOT rebuilt and jm-forex.service was NOT restarted."
echo "    Open: https://jmtechsolution.cloud/lab/#trade"
echo "    Per-pair: https://jmtechsolution.cloud/lab/EURUSD (GBPUSD, AUDNZD, EURCHF, XAUUSD)"
