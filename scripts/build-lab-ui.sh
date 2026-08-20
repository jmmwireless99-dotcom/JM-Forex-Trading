#!/usr/bin/env bash
# Build JM Lab UI only — does NOT touch JM FX frontend or backend static.
# Output: lab-ui/dist/ (deploy to /lab/ on nginx or any static host)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/lab-ui"

if [[ -f package-lock.json ]]; then
  npm ci --silent
else
  npm install --silent
fi

JM_LAB_BASE="${JM_LAB_BASE:-/lab/}" npm run build

echo "OK: lab-ui built → $ROOT/lab-ui/dist"
echo "Deploy: copy lab-ui/dist/* to your web root /lab/ (nginx alias recommended)"
