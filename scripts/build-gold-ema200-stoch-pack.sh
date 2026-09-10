#!/usr/bin/env bash
# Build JM-GOLD-EMA200-STOCH-Pack.zip — clean 2-indicator gold scalper
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-GOLD-EMA200-STOCH-Pack"
ZIP="$ROOT/releases/JM-GOLD-EMA200-STOCH-Pack.zip"

mkdir -p "$SRC/Experts"
cp "$ROOT/mt5/Experts/JM_GOLD_EMA200_STOCH_SCALPER.mq5" "$SRC/Experts/"
cp "$ROOT/mt5/JM_GOLD_EMA200_STOCH_SETUP.txt" "$SRC/SETUP.txt"
cp "$ROOT/mt5/JM_GOLD_EMA200_STOCH_SETUP.txt" "$SRC/README.txt"

cat > "$SRC/VERSION.txt" <<EOF
JM-GOLD-EMA200-STOCH-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EA: JM_GOLD_EMA200_STOCH_SCALPER.mq5
EA version: 1.00
Build tag: EMA200-STOCH-SCALEOUT-v1
Symbol: GOLD#
Lots: 0.03 (three 0.01 scale-out legs)
SL/TP: gold price \$ 3.50 / 5 / 10 / 15
NOT V6.1 — do not attach with V6.1 on the same chart
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP"
