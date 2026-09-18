#!/usr/bin/env bash
# Build JM-GOLD-V677-Pack.zip — V6.77 trading EA + analyzer includes
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-GOLD-V677-Pack"
ZIP="$ROOT/releases/JM-GOLD-V677-Pack.zip"

mkdir -p "$SRC/Experts"
cp "$ROOT/mt5/Experts/JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V6_77.mq5" "$SRC/Experts/"
cp "$ROOT/mt5/Experts/JM_GOLD_V656_CompleteAnalyzer.mqh" "$SRC/Experts/"
cp "$ROOT/mt5/Experts/JM_GOLD_V680_LossRootCauseAnalyzer.mqh" "$SRC/Experts/"
cp "$ROOT/mt5/JM_GOLD_V677_SETUP.txt" "$SRC/SETUP.txt"
cp "$ROOT/mt5/JM_GOLD_V677_SETUP.txt" "$SRC/README.txt"

cat > "$SRC/VERSION.txt" <<EOF
JM-GOLD-V677-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EA: JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V6_77.mq5
EA version: 6.77
Build tag: V6.77-BEST-MASTER-SL15
Magic: 26091077
Includes (keep next to EA):
  JM_GOLD_V656_CompleteAnalyzer.mqh
  JM_GOLD_V680_LossRootCauseAnalyzer.mqh
Symbol: GOLD#
Lots: 0.01
SL: \$15 @ 0.01 (scales with lot)
NOT V6.1 — do not overwrite V4_2.mq5
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP"
