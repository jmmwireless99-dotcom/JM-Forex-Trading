#!/usr/bin/env bash
# Build JM-THUNDER-GOLD-SCALPER-Pack.zip — Thunder V2.0.3 + manual trail
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-THUNDER-GOLD-SCALPER-Pack"
ZIP="$ROOT/releases/JM-THUNDER-GOLD-SCALPER-Pack.zip"

mkdir -p "$SRC/Experts"
cp "$ROOT/mt5/Experts/JM_THUNDER_GOLD_SCALPER.mq5" "$SRC/Experts/"
cp "$ROOT/mt5/JM_THUNDER_GOLD_SCALPER_SETUP.txt" "$SRC/SETUP.txt"
cp "$ROOT/mt5/JM_THUNDER_GOLD_SCALPER_SETUP.txt" "$SRC/README.txt"
cp "$ROOT/scripts/copy-thunder-to-vantage-experts.bat" "$SRC/COPY-TO-VANTAGE-MT5.bat"

cat > "$SRC/VERSION.txt" <<EOF
JM-THUNDER-GOLD-SCALPER-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EA: JM_THUNDER_GOLD_SCALPER.mq5
EA version: 2.0.3
Build tag: THUNDER-V2.0.3-MANUAL-TRAIL
Magic auto: 30250003
Magic manual: 0
Symbol: GOLD# / XAUUSD
Trail start: \$0.50 @ 0.01 lot
Trail distance: \$0.70 (70 pts original Thunder)
Trail step: \$0.10
Manual: BUY/SELL STOP + LIMIT, keep user SL/TP, auto-trail after fill
NO grid / NO martingale
NOT V6.1 and NOT V6.77
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP"
