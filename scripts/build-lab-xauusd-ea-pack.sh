#!/usr/bin/env bash
# Build JM-Lab-XAUUSD-MT5-EA.zip for download
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACK="$ROOT/releases/JM-Lab-XAUUSD-MT5-EA"
ZIP="$ROOT/releases/JM-Lab-XAUUSD-MT5-EA.zip"

echo "==> Sync EA source..."
mkdir -p "$PACK/Experts"
cp "$ROOT/mt5/Experts/JM_Lab_XAUUSD_EA.mq5" "$PACK/Experts/"

echo "==> Building zip..."
rm -f "$ZIP"
(cd "$PACK" && zip -qr "$ZIP" .)

echo "==> Done: $ZIP"
ls -lh "$ZIP"
