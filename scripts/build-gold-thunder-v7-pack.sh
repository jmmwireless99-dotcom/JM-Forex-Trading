#!/usr/bin/env bash
# Build JM-THUNDER-GOLD-SCALPER-V7-Pack.zip — V7 + Desktop copy BAT
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-THUNDER-GOLD-SCALPER-V7-Pack"
ZIP="$ROOT/releases/JM-THUNDER-GOLD-SCALPER-V7-Pack.zip"

mkdir -p "$SRC/Experts"
cp "$ROOT/mt5/Experts/JM_THUNDER_GOLD_SCALPER_V7.mq5" "$SRC/Experts/"
cp "$ROOT/mt5/JM_THUNDER_GOLD_SCALPER_V7_SETUP.txt" "$SRC/SETUP.txt"
cp "$ROOT/mt5/JM_THUNDER_GOLD_SCALPER_V7_SETUP.txt" "$SRC/README.txt"
cp "$ROOT/scripts/copy-thunder-v7-to-desktop.bat" "$SRC/COPY-TO-DESKTOP.bat"
# Ready-to-drop Desktop folder inside the zip
mkdir -p "$SRC/Desktop/JM-THUNDER-GOLD-SCALPER-V7"
cp "$ROOT/mt5/Experts/JM_THUNDER_GOLD_SCALPER_V7.mq5" "$SRC/Desktop/JM-THUNDER-GOLD-SCALPER-V7/"
cp "$ROOT/mt5/JM_THUNDER_GOLD_SCALPER_V7_SETUP.txt" "$SRC/Desktop/JM-THUNDER-GOLD-SCALPER-V7/SETUP.txt"
cp "$ROOT/mt5/Experts/JM_THUNDER_GOLD_SCALPER_V7.mq5" "$SRC/Desktop/"

cat > "$SRC/VERSION.txt" <<EOF
JM-THUNDER-GOLD-SCALPER-V7-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EA: JM_THUNDER_GOLD_SCALPER_V7.mq5
EA version: 7.0.0
Build tag: THUNDER-V7-FAST-TRAIL
Magic auto: 30250007
Magic manual: 0
Trail start: \$0.50 @ 0.01
Trail distance: \$0.70
Trail step: every tick (fast / extreme pitik follow)
FastEntry: ON
FastTrail: ON
TrailReplacesSL: ON (once trailing, SL = trail only)
Auto Thunder: ALWAYS ON
Manual: STOP/LIMIT trail after fill, keep user SL/TP until trail arms
NO grid / NO martingale
Put on Desktop: run COPY-TO-DESKTOP.bat
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP"
