#!/usr/bin/env bash
# Rebuild frontend for https://jmtechsolution.cloud/fx/ and restart systemd service.
# Usage on VPS:
#   cd /opt/jm-forex-trading && ./scripts/deploy-fx-portal.sh
#   BRANCH=cursor/ai-ml-trade-assist-c11c ./scripts/deploy-fx-portal.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${BRANCH:-main}"

echo "[1/5] Fetch + checkout ${BRANCH}..."
git fetch origin "${BRANCH}"
git checkout -B "${BRANCH}" "origin/${BRANCH}"
git reset --hard "origin/${BRANCH}"

echo "[2/5] Ensure AI_ML runtime env..."
ENV_FILE="$ROOT/.env"
touch "$ENV_FILE"
# Upsert key AI_ML settings without wiping other secrets
upsert_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >>"$ENV_FILE"
  fi
}
upsert_env JM_DEFAULT_STRATEGY AI_ML
upsert_env JM_AUTO_STRATEGY true
upsert_env JM_AI_ASSIST true
upsert_env JM_AI_GATE_ENTRIES true
upsert_env JM_AI_MIN_WIN_PROB 0.40
# Block SMC SELL overlap only after weak WR (not cold-start freeze)
upsert_env JM_AI_BLOCK_SMC_SELL_OVERLAP true
upsert_env JM_AI_SMC_SELL_OVERLAP_MIN_WR 0.35
upsert_env JM_AI_SMC_SELL_OVERLAP_MIN_N 5
# One desk signal → every follow_auto paper account (centralized fan-out)
upsert_env JM_AUTO_FILL_SINGLE_BOOK false
upsert_env JM_EXECUTION_MODE paper
upsert_env JM_DEFAULT_SYMBOLS XAUUSD
# XM MT4 live gold symbol (desk still uses XAUUSD internally)
grep -q '^JM_MT4_SYMBOL=' "$ENV_FILE" 2>/dev/null || upsert_env JM_MT4_SYMBOL GOLD
upsert_env JM_ASIA_DESK_ONLY true
# Investment dashboard (do not overwrite JM_INVEST_SECRET if present)
grep -q '^JM_INVEST_SECRET=' "$ENV_FILE" 2>/dev/null || upsert_env JM_INVEST_SECRET "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
upsert_env JM_INVEST_ADMIN_EMAIL admin@jmfx.local
upsert_env JM_INVEST_ADMIN_NAME "JM FX Admin"
upsert_env JM_INVEST_DEMO_ENABLED false
upsert_env JM_INVEST_PERIOD_RATE 0.30
upsert_env JM_INVEST_PERIOD_DAYS 30

echo "[3/5] Build frontend with base=/fx/ ..."
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm ci --silent
else
  npm ci --silent
fi
JM_BASE=/fx/ npm run build

echo "[4/5] Publish static assets..."
rm -rf "$ROOT/backend/static"
mkdir -p "$ROOT/backend/static"
cp -a "$ROOT/frontend/dist/." "$ROOT/backend/static/"

# Sanity: asset paths must be under /fx/
if ! grep -q '/fx/assets/' "$ROOT/backend/static/index.html"; then
  echo "ERROR: index.html missing /fx/assets/ base — refusing deploy"
  grep -E 'src=|href=' "$ROOT/backend/static/index.html" || true
  exit 1
fi

# Ensure Python deps include sklearn for AI_ML
if [[ -x "$ROOT/backend/.venv/bin/pip" ]]; then
  "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
elif [[ -x /opt/jm-forex-trading/backend/.venv/bin/pip ]]; then
  /opt/jm-forex-trading/backend/.venv/bin/pip install -q -r "$ROOT/backend/requirements.txt"
fi

echo "[5/6] Sync systemd env (systemd overrides .env for jm-forex)..."
UNIT="/etc/systemd/system/jm-forex.service"
if [[ -f "$UNIT" ]]; then
  sed -i 's/^Environment=JM_AUTO_FILL_SINGLE_BOOK=.*/Environment=JM_AUTO_FILL_SINGLE_BOOK=false/' "$UNIT"
  if grep -q '^Environment=JM_ASIA_DESK_ONLY=' "$UNIT"; then
    sed -i 's/^Environment=JM_ASIA_DESK_ONLY=.*/Environment=JM_ASIA_DESK_ONLY=true/' "$UNIT"
  else
    sed -i '/^Environment=JM_AUTO_FILL/a Environment=JM_ASIA_DESK_ONLY=true' "$UNIT"
  fi
  if grep -q '^Environment=JM_MT_BRIDGE_TOKEN=' "$UNIT"; then
    MT4_CODE=$(grep '^JM_MT4_REAL_ACCOUNT_CODE=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    MT4_DIR=$(grep '^JM_MT4_REAL_BRIDGE_DIR=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    if [[ -n "$MT4_CODE" && -n "$MT4_DIR" ]]; then
      grep -q '^Environment=JM_MT4_REAL_ACCOUNT_CODE=' "$UNIT" || \
        sed -i "/^Environment=JM_MT_BRIDGE_TOKEN=/a Environment=JM_MT4_REAL_ACCOUNT_CODE=${MT4_CODE}" "$UNIT"
      grep -q '^Environment=JM_MT4_REAL_BRIDGE_DIR=' "$UNIT" || \
        sed -i "/^Environment=JM_MT4_REAL_ACCOUNT_CODE=/a Environment=JM_MT4_REAL_BRIDGE_DIR=${MT4_DIR}" "$UNIT"
      MT4_SYM=$(grep '^JM_MT4_SYMBOL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo GOLD)
      MT4_SYM="${MT4_SYM:-GOLD}"
      if grep -q '^Environment=JM_MT4_SYMBOL=' "$UNIT"; then
        sed -i "s/^Environment=JM_MT4_SYMBOL=.*/Environment=JM_MT4_SYMBOL=${MT4_SYM}/" "$UNIT"
      else
        sed -i "/^Environment=JM_MT4_REAL_BRIDGE_DIR=/a Environment=JM_MT4_SYMBOL=${MT4_SYM}" "$UNIT"
      fi
    fi
  fi
  systemctl daemon-reload
fi

echo "[6/6] Restart jm-forex..."
systemctl restart jm-forex.service
sleep 3
systemctl is-active jm-forex.service
curl -fsS http://127.0.0.1:8000/api/health
echo
curl -fsS http://127.0.0.1:8000/api/status | python3 -c 'import sys,json;d=json.load(sys.stdin);print("strategy=",d.get("active_strategy"),"running=",d.get("running"))'
curl -fsS http://127.0.0.1:8000/api/ai/status | python3 -c 'import sys,json;d=json.load(sys.stdin);print("ai=",d.get("name"),"backend=",(d.get("model") or {}).get("backend"))'
echo
echo "OK — open https://jmtechsolution.cloud/fx/"
