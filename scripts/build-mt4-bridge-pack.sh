#!/usr/bin/env bash
# Build JM-FX-MT4-Bridge-Pack.zip and JM-FX-MT4-EA-v2.zip
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACK="$ROOT/releases/JM-FX-MT4-Bridge-Pack"
EA_V2="$ROOT/releases/JM-FX-MT4-EA-v2"
REAL="$ROOT/releases/JM-FX-MT4-Real-EA-v2"
MQ4="$ROOT/mt4/Experts/JM_Forex_Bridge.mq4"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$PACK/Experts" "$EA_V2/Experts" "$REAL/Experts"
cp "$MQ4" "$PACK/Experts/"
cp "$MQ4" "$EA_V2/Experts/"
cp "$MQ4" "$REAL/Experts/"

cat > "$PACK/VERSION.txt" <<EOF
JM-FX-MT4-Bridge-Pack
Built: $STAMP
EA version: 2.00
Modes: cloud (MT4 real) + local file (MT4 demo)
Symbol: GOLD (demo) / XAUUSD (real)
EOF

cat > "$EA_V2/VERSION.txt" <<EOF
JM-FX-MT4-EA-v2
Built: $STAMP
EA version: 2.00
Mode: cloud direct (MT4 real, no PC agent)
EOF

cp "$PACK/SETUP-NO-AGENT.txt" "$EA_V2/SETUP-NO-AGENT.txt"
cp "$PACK/JM-FX-MT4-ACCOUNTS.txt" "$EA_V2/JM-FX-ACCOUNT.txt"

for name in JM-FX-MT4-Bridge-Pack JM-FX-MT4-EA-v2 JM-FX-MT4-Real-EA-v2; do
  ZIP="$ROOT/releases/${name}.zip"
  rm -f "$ZIP"
  (cd "$ROOT/releases/$name" && zip -qr "$ZIP" .)
  echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
done
