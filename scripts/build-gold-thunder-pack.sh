#!/usr/bin/env bash
# Build JM-THUNDER-GOLD-SCALPER-Pack.zip — Thunder V1.0.0 single-file EA
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-THUNDER-GOLD-SCALPER-Pack"
ZIP="$ROOT/releases/JM-THUNDER-GOLD-SCALPER-Pack.zip"

mkdir -p "$SRC/Experts"
cp "$ROOT/mt5/Experts/JM_THUNDER_GOLD_SCALPER.mq5" "$SRC/Experts/"
cp "$ROOT/mt5/JM_THUNDER_GOLD_SCALPER_SETUP.txt" "$SRC/SETUP.txt"
cp "$ROOT/mt5/JM_THUNDER_GOLD_SCALPER_SETUP.txt" "$SRC/README.txt"

cat > "$SRC/VERSION.txt" <<EOF
JM-THUNDER-GOLD-SCALPER-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EA: JM_THUNDER_GOLD_SCALPER.mq5
EA version: 1.0.0
Build tag: THUNDER-V1.0.0-NOGRID
Magic: 26100610
Symbol: GOLD#
Lots: 0.01
SL: \$15 @ 0.01 (scales with lot)
TP: \$30 base / \$45 strong
NO grid / NO martingale / one trade
NOT V6.1 and NOT V6.77
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP"
