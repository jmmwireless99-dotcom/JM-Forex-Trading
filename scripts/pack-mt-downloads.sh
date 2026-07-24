#!/usr/bin/env bash
# Pack MT4/MT5 bridge downloads into backend/static/downloads/
# Usage: ./scripts/pack-mt-downloads.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/backend/static/downloads"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$OUT"

# --- Standalone EAs ---
cp -f "$ROOT/mt5/Experts/JM_Forex_Bridge.mq5" "$OUT/JM_Forex_Bridge.mq5"
if [[ -f "$ROOT/mt4/Experts/JM_Forex_Bridge.mq4" ]]; then
  cp -f "$ROOT/mt4/Experts/JM_Forex_Bridge.mq4" "$OUT/JM_Forex_Bridge.mq4"
fi

# --- Dual agent zip (existing URL) ---
DUAL="$TMP/jm-mt-agent"
mkdir -p "$DUAL"
cp -f "$ROOT/mt5/agent/"*.py "$ROOT/mt5/agent/"*.ps1 "$ROOT/mt5/agent/"*.bat "$ROOT/mt5/agent/"*.json "$ROOT/mt5/agent/"*.md "$DUAL/" 2>/dev/null || true
cp -f "$ROOT/mt5/agent/SETUP_MT5.txt" "$DUAL/" 2>/dev/null || true
cp -f "$ROOT/mt5/Experts/JM_Forex_Bridge.mq5" "$DUAL/"
if [[ -f "$ROOT/mt4/Experts/JM_Forex_Bridge.mq4" ]]; then
  cp -f "$ROOT/mt4/Experts/JM_Forex_Bridge.mq4" "$DUAL/"
fi
( cd "$TMP" && zip -qr "$OUT/jm-mt-agent.zip" jm-mt-agent )

# --- MT5-only zip (bagong bridge) ---
MT5="$TMP/jm-mt5-bridge"
mkdir -p "$MT5"
cp -f "$ROOT/mt5/Experts/JM_Forex_Bridge.mq5" "$MT5/"
cp -f "$ROOT/mt5/agent/jm_mt_agent.py" "$MT5/"
cp -f "$ROOT/mt5/agent/jm_mt_agent.ps1" "$MT5/"
cp -f "$ROOT/mt5/agent/RUN_AGENT_MT5.bat" "$MT5/"
cp -f "$ROOT/mt5/agent/config.mt5.json" "$MT5/"
cp -f "$ROOT/mt5/agent/config.example.json" "$MT5/" 2>/dev/null || true
cp -f "$ROOT/mt5/agent/SETUP_MT5.txt" "$MT5/"
# Seed config.json from mt5 preset so first run works
cp -f "$ROOT/mt5/agent/config.mt5.json" "$MT5/config.json"
( cd "$TMP" && zip -qr "$OUT/jm-mt5-bridge.zip" jm-mt5-bridge )

echo "Packed downloads → $OUT"
ls -la "$OUT"
