#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-GOLD-V620-TP30-Pack"
ZIP="$ROOT/releases/JM-GOLD-V620-TP30-Pack.zip"

mkdir -p "$SRC/Experts"
cp "$ROOT/mt5/Experts/JM_GOLD_V6_20_TP30_SL15.mq5" "$SRC/Experts/"
cp "$ROOT/mt5/JM_GOLD_V6_20_SETUP.txt" "$SRC/SETUP.txt"
cp "$ROOT/mt5/JM_GOLD_V6_20_SETUP.txt" "$SRC/README.txt"

cat > "$SRC/VERSION.txt" <<EOF
JM-GOLD-V620-TP30-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EA: JM_GOLD_V6_20_TP30_SL15.mq5
EA version: 6.20
Build tag: V6.20-TP30-SL15-H21BLOCK-STRONGTREND
Adds: H21 SELL block + strong-trend score boost
NOT V6.1 and NOT EMA200-STOCH
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP"
