#!/usr/bin/env bash
# Enable remote MT5 bridge on JM FX VPS (run once on server or via remote-deploy).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRIDGE_DIR="${JM_MT5_BRIDGE_DIR:-/opt/jm-forex-trading/mt5_bridge}"
ACCOUNT_CODE="${JM_MT5_DEMO_ACCOUNT_CODE:-DDDC3D}"
SYMBOL="${JM_MT_SYMBOL:-GOLD24-7#}"
TOKEN="${JM_MT_BRIDGE_TOKEN:-gTXmD7O-194jS9gveB1I5c9qjmNdqdUv}"

mkdir -p "$BRIDGE_DIR"

upsert_env_file() {
  local file="$1" key="$2" val="$3"
  touch "$file"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$file"
  else
    echo "${key}=${val}" >>"$file"
  fi
}

upsert_systemd() {
  local key="$1" val="$2"
  local unit="/etc/systemd/system/jm-forex.service"
  [[ -f "$unit" ]] || return 0
  if grep -q "^Environment=${key}=" "$unit"; then
    sed -i "s|^Environment=${key}=.*|Environment=${key}=${val}|" "$unit"
  else
    sed -i "/^\[Service\]/a Environment=${key}=${val}" "$unit"
  fi
}

ENV_FILE="$ROOT/.env"
upsert_env_file "$ENV_FILE" JM_EXECUTION_MODE mt5
upsert_env_file "$ENV_FILE" JM_MT5_BRIDGE_DIR "$BRIDGE_DIR"
upsert_env_file "$ENV_FILE" JM_MT5_DEMO_ACCOUNT_CODE "$ACCOUNT_CODE"
upsert_env_file "$ENV_FILE" JM_MT_SYMBOL "$SYMBOL"
upsert_env_file "$ENV_FILE" JM_MT_REMOTE_BRIDGE true
upsert_env_file "$ENV_FILE" JM_MT_BRIDGE_TOKEN "$TOKEN"

for kv in \
  "JM_EXECUTION_MODE=mt5" \
  "JM_MT5_BRIDGE_DIR=${BRIDGE_DIR}" \
  "JM_MT5_DEMO_ACCOUNT_CODE=${ACCOUNT_CODE}" \
  "JM_MT_SYMBOL=${SYMBOL}" \
  "JM_MT_REMOTE_BRIDGE=true" \
  "JM_MT_BRIDGE_TOKEN=${TOKEN}"; do
  upsert_systemd "${kv%%=*}" "${kv#*=}"
done

systemctl daemon-reload
systemctl restart jm-forex.service
sleep 3

echo "Bridge dir: $BRIDGE_DIR"
echo "Account code: $ACCOUNT_CODE"
echo "Symbol: $SYMBOL"
curl -fsS http://127.0.0.1:8000/api/mt/status | python3 -m json.tool || true
echo
echo "Next: run scripts/start-jm-mt5-agent.bat on Windows PC with MT5 open"
