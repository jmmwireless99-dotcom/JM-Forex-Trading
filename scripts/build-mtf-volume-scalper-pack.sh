#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACK="$ROOT/releases/JM-MTF-Volume-Scalper-EA"
ZIP="$ROOT/releases/JM-MTF-Volume-Scalper-EA.zip"
mkdir -p "$PACK/Experts"
cp "$ROOT/mt5/Experts/JM_MTF_Volume_Profile_Scalper.mq5" "$PACK/Experts/"
cp "$PACK/README.txt" "$PACK/README.txt" 2>/dev/null || cp "$ROOT/releases/JM-MTF-Volume-Scalper-EA/README.txt" "$PACK/" 2>/dev/null || true
rm -f "$ZIP"
(cd "$PACK" && zip -qr "$ZIP" .)
echo "Built $ZIP"
