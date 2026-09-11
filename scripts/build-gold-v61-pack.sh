#!/usr/bin/env bash
# Build JM-GOLD-V61-Analyzer-Pack.zip — V6.1 gold scalper + live OK/MALI panel
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-GOLD-V61-Analyzer-Pack"
ZIP="$ROOT/releases/JM-GOLD-V61-Analyzer-Pack.zip"

mkdir -p "$SRC/Experts" "$SRC/Include"
cp "$ROOT/mt5/Experts/JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V4_2.mq5" "$SRC/Experts/"
cp "$ROOT/mt5/Include/JM_V61_LiveAnalyzer.mqh" "$SRC/Include/"
cp "$ROOT/mt5/JM_Gold_Flow_Analyzer_SETUP.txt" "$SRC/SETUP.txt"

cat > "$SRC/VERSION.txt" <<EOF
JM-GOLD-V61-Analyzer-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EA: JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V4_2.mq5
EA version: 6.10
Build tag: V6.1-FINAL-H16-H17-BLOCK
Analyzer: JM_V61_LiveAnalyzer.mqh (display only)
Symbol: GOLD#
Lots: 0.01
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP"
