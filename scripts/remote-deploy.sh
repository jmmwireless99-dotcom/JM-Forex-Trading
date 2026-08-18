#!/usr/bin/env bash
# Run deploy-fx-portal.sh on the live VPS over SSH.
#
# Required env:
#   JM_VPS_HOST   (default 72.62.73.235)
#   JM_VPS_USER   (e.g. root or ubuntu)
# And ONE of:
#   JM_VPS_SSH_KEY     path to private key
#   JM_VPS_SSH_PASSWORD  (needs sshpass)
#
# Optional:
#   BRANCH=cursor/restore-aiml-trade-freq-073b
#   JM_VPS_DIR=/opt/jm-forex-trading
set -euo pipefail

HOST="${JM_VPS_HOST:-72.62.73.235}"
USER="${JM_VPS_USER:?Set JM_VPS_USER (e.g. root)}"
DIR="${JM_VPS_DIR:-/opt/jm-forex-trading}"
BRANCH="${BRANCH:-cursor/restore-aiml-trade-freq-073b}"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

if [[ -n "${JM_VPS_SSH_KEY:-}" ]]; then
  SSH_OPTS+=(-i "$JM_VPS_SSH_KEY")
  SSH=(ssh "${SSH_OPTS[@]}" "${USER}@${HOST}")
elif [[ -n "${JM_VPS_SSH_PASSWORD:-}" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "sshpass required for password auth — install it or use JM_VPS_SSH_KEY"
    exit 1
  fi
  SSH=(sshpass -p "$JM_VPS_SSH_PASSWORD" ssh "${SSH_OPTS[@]}" -o PreferredAuthentications=password -o PubkeyAuthentication=no "${USER}@${HOST}")
else
  echo "Set JM_VPS_SSH_KEY or JM_VPS_SSH_PASSWORD"
  exit 1
fi

echo "Deploying ${BRANCH} → ${USER}@${HOST}:${DIR}"
"${SSH[@]}" "set -euo pipefail
  cd '${DIR}'
  export BRANCH='${BRANCH}'
  git remote -v
  chmod +x scripts/deploy-fx-portal.sh
  ./scripts/deploy-fx-portal.sh
"

echo "Live check..."
curl -fsS "https://jmtechsolution.cloud/fx/api/health"
echo
curl -fsS "https://jmtechsolution.cloud/fx/api/status" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("active_strategy"), d.get("running"))'
curl -fsS "https://jmtechsolution.cloud/fx/api/ai/status" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("name"), (d.get("model") or {}).get("backend"))'
