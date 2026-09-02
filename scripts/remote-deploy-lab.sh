#!/usr/bin/env bash
# Deploy JM Lab to VPS over SSH — never runs deploy-fx-portal.sh.
#
# IMPORTANT: Lab uses its own git worktree (JM_VPS_LAB_DIR, default
# /opt/jm-lab-src) — completely separate checkout from the JM FX repo
# (JM_VPS_DIR, /opt/jm-forex-trading). Both scripts used to `git checkout`
# the SAME directory, so a Lab deploy would silently switch the on-disk
# source for jm-forex.service too — harmless only until that service ever
# restarts, at which point it reloads whatever branch Lab last checked out.
# The worktree keeps the two checkouts (and running services) independent.
set -euo pipefail

HOST="${JM_VPS_HOST:-72.62.73.235}"
USER="${JM_VPS_USER:?Set JM_VPS_USER (e.g. root)}"
FX_DIR="${JM_VPS_DIR:-/opt/jm-forex-trading}"
DIR="${JM_VPS_LAB_DIR:-/opt/jm-lab-src}"
BRANCH="${BRANCH:-cursor/lab-demo-trading-c11c}"

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
  FX_DIR='${FX_DIR}'
  DIR='${DIR}'
  export BRANCH='${BRANCH}'

  # One-time: create the isolated Lab worktree (does not touch \$FX_DIR's checkout).
  if [[ ! -d \"\$DIR/.git\" && ! -f \"\$DIR/.git\" ]]; then
    echo '[0/5] Creating isolated Lab worktree at' \"\$DIR\" '...'
    git -C \"\$FX_DIR\" fetch origin \"\$BRANCH\"
    git -C \"\$FX_DIR\" worktree add \"\$DIR\" -B \"\$BRANCH\" \"origin/\$BRANCH\" 2>/dev/null \\
      || git -C \"\$FX_DIR\" worktree add \"\$DIR\" \"origin/\$BRANCH\" --detach

    # Migrate existing Lab data (trade history) from the old shared checkout
    # into the new isolated worktree — one-time, only if not already present.
    if [[ -f \"\$FX_DIR/lab-backend/data/lab_accounts.json\" && ! -f \"\$DIR/lab-backend/data/lab_accounts.json\" ]]; then
      echo 'Migrating existing lab_accounts.json into the new worktree...'
      mkdir -p \"\$DIR/lab-backend/data\"
      cp -a \"\$FX_DIR/lab-backend/data/lab_accounts.json\" \"\$DIR/lab-backend/data/lab_accounts.json\"
    fi
  fi

  cd \"\$DIR\"
  chmod +x scripts/deploy-lab-portal.sh scripts/deploy-lab-backend.sh scripts/install-apache-lab-snippet.sh 2>/dev/null || true
  if [[ -x scripts/install-apache-lab-snippet.sh ]]; then
    ./scripts/install-apache-lab-snippet.sh || true
  fi
  ./scripts/deploy-lab-portal.sh
"

echo "Smoke checks..."
curl -fsS "https://jmtechsolution.cloud/fx/api/health" >/dev/null && echo "JM FX health: OK"
LAB_CODE=$(curl -sS -o /dev/null -w '%{http_code}' "https://jmtechsolution.cloud/lab/")
echo "JM Lab /lab/: HTTP ${LAB_CODE}"
LAB_API=$(curl -sS -o /tmp/lab-health.json -w '%{http_code}' "https://jmtechsolution.cloud/lab/api/health")
echo "JM Lab /lab/api/health: HTTP ${LAB_API}"
if [[ "$LAB_CODE" != "200" ]]; then
  echo "Lab may need Apache snippet — run install-apache-lab-snippet.sh on VPS"
  exit 1
fi
if [[ "$LAB_API" != "200" ]] || ! grep -q '"JM Lab Trading"' /tmp/lab-health.json 2>/dev/null; then
  echo "Lab API not reachable — check jm-lab.service and Apache /lab/api/ proxy"
  cat /tmp/lab-health.json 2>/dev/null | head -3 || true
  exit 1
fi
