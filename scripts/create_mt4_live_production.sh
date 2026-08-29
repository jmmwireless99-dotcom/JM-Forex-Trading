#!/usr/bin/env bash
# Create MT4 live JM FX account on production without the running service overwriting it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/backend/.venv/bin/python3"
CODE="${1:-A76321}"
TOKEN="${2:-}"

echo "==> Stop jm-forex (prevent in-memory save wiping new account)..."
systemctl stop jm-forex.service

ARGS=(--label "XM MT4 Live" --code "$CODE")
if [[ -n "$TOKEN" ]]; then
  ARGS+=(--token "$TOKEN")
fi

echo "==> Create / update MT4 live account..."
"$PY" "$ROOT/scripts/create_xm_mt4_real_account.py" "${ARGS[@]}"

echo "==> Start jm-forex..."
systemctl start jm-forex.service
sleep 4

if [[ -n "$TOKEN" ]]; then
  curl -fsS -X POST http://127.0.0.1:8000/api/accounts/login \
    -H "Content-Type: application/json" \
    -d "{\"code\":\"${CODE}\",\"token\":\"${TOKEN}\"}" | python3 -m json.tool | head -12
else
  echo "Account created. Use the token printed above to login."
fi
