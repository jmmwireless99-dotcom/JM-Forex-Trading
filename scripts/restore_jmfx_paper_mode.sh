#!/usr/bin/env bash
# Emergency restore: paper mode + live gold (fixes desk when MT5 agent not running).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
UNIT="/etc/systemd/system/jm-forex.service"

upsert_env_file() {
  local key="$1" val="$2"
  touch "$ENV_FILE"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >>"$ENV_FILE"
  fi
}

upsert_systemd() {
  local key="$1" val="$2"
  [[ -f "$UNIT" ]] || return 0
  if grep -q "^Environment=${key}=" "$UNIT"; then
    sed -i "s|^Environment=${key}=.*|Environment=${key}=${val}|" "$UNIT"
  fi
}

upsert_env_file JM_EXECUTION_MODE paper
upsert_systemd JM_EXECUTION_MODE paper

systemctl daemon-reload
systemctl restart jm-forex.service
sleep 3
curl -fsS http://127.0.0.1:8000/api/status | python3 -c \
  'import sys,json;d=json.load(sys.stdin);print("mode=",d.get("mode"),"mid=",d.get("connection",{}).get("paper_mid"))'
echo "OK — paper mode restored"
