#!/usr/bin/env bash
# Deploy JM Lab to VPS over SSH — never runs deploy-fx-portal.sh.
set -euo pipefail

HOST="${JM_VPS_HOST:-72.62.73.235}"
USER="${JM_VPS_USER:?Set JM_VPS_USER (e.g. root)}"
DIR="${JM_VPS_DIR:-/opt/jm-forex-trading}"
BRANCH="${BRANCH:-cursor/experiment-lab-ui-c11c}"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

if [[ -n "${JM_VPS_SSH_KEY:-}" ]]; then
  SSH_OPTS+=(-i "$JM_VPS_SSH_KEY")
  SSH=(ssh "${SSH_OPTS[@]}" "${USER}@${HOST}")
elif [[ -n "${JM_VPS_SSH_PASSWORD:-}" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "sshpass required — install it or use JM_VPS_SSH_KEY"
    exit 1
  fi
  SSH=(sshpass -p "$JM_VPS_SSH_PASSWORD" ssh "${SSH_OPTS[@]}" -o PreferredAuthentications=password -o PubkeyAuthentication=no "${USER}@${HOST}")
else
  echo "Set JM_VPS_SSH_KEY or JM_VPS_SSH_PASSWORD"
  exit 1
fi

echo "Deploying JM Lab only (${BRANCH}) → ${USER}@${HOST}"
"${SSH[@]}" "set -euo pipefail
  cd '${DIR}'
  export BRANCH='${BRANCH}'
  chmod +x scripts/deploy-lab-portal.sh scripts/install-apache-lab-snippet.sh 2>/dev/null || true
  if [[ -x scripts/install-apache-lab-snippet.sh ]]; then
    ./scripts/install-apache-lab-snippet.sh || true
  fi
  ./scripts/deploy-lab-portal.sh
"

echo "Smoke checks..."
curl -fsS "https://jmtechsolution.cloud/fx/api/health" >/dev/null && echo "JM FX health: OK"
LAB_CODE=$(curl -sS -o /dev/null -w '%{http_code}' "https://jmtechsolution.cloud/lab/")
echo "JM Lab /lab/: HTTP ${LAB_CODE}"
if [[ "$LAB_CODE" != "200" ]]; then
  echo "Lab may need Apache snippet — run install-apache-lab-snippet.sh on VPS"
  exit 1
fi
