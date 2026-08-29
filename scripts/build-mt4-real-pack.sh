#!/usr/bin/env bash
# Build JM-FX-MT4-Real-EA-v2.zip — MT4 real cloud EA (no PC agent)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-FX-MT4-Real-EA-v2"
ZIP="$ROOT/releases/JM-FX-MT4-Real-EA-v2.zip"

mkdir -p "$SRC/Experts"
cp "$ROOT/mt4/Experts/JM_Forex_Bridge.mq4" "$SRC/Experts/"

cat > "$SRC/VERSION.txt" <<EOF
JM-FX-MT4-Real-EA-v2
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EA version: 2.00
Mode: cloud direct (no PC agent)
Symbol: XAUUSD
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
