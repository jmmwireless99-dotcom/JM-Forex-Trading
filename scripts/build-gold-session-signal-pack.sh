#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/releases/JM-GOLD-Session-Signal-Pack"
ZIP="$ROOT/releases/JM-GOLD-Session-Signal-Pack.zip"

mkdir -p "$SRC/Indicators"
cp "$ROOT/mt5/Indicators/JM_GOLD_Session_Signal_v1.mq5" "$SRC/Indicators/"
cp "$ROOT/mt5/JM_GOLD_Session_Signal_SETUP.txt" "$SRC/SETUP.txt"
cp "$ROOT/mt5/JM_GOLD_Session_Signal_SETUP.txt" "$SRC/README.txt"

cat > "$SRC/VERSION.txt" <<EOF
JM-GOLD-Session-Signal-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Indicator: JM_GOLD_Session_Signal_v1.mq5
Version: 1.00
NO ORDERS — visual + CSV reason log only
Copy to MQL5\\\\Indicators\\\\  (not Experts)
EOF

rm -f "$ZIP"
(cd "$SRC" && zip -qr "$ZIP" .)
echo "==> $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP"
