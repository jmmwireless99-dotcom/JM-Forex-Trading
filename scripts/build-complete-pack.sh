#!/usr/bin/env bash
# Build JM-FX-Complete-Pack.zip — all Windows files + portable Python embeddable
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACK="$ROOT/releases/JM-FX-Complete-Pack"
STAGE="$ROOT/releases/.build-complete-pack"
ZIP="$ROOT/releases/JM-FX-Complete-Pack.zip"

PYTHON_VER="3.12.7"
PYTHON_ZIP="python-${PYTHON_VER}-embed-amd64.zip"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VER}/${PYTHON_ZIP}"

echo "==> Staging complete pack..."
rm -rf "$STAGE"
mkdir -p "$STAGE"

# Copy pack skeleton
cp -r "$PACK/README.txt" "$PACK/DOWNLOAD-LINKS.txt" "$PACK/install-python.ps1" \
  "$PACK/install-python.bat" "$PACK/start-jm-mt5-agent.bat" "$STAGE/"
cp -r "$PACK/accounts" "$PACK/mt4/SETUP.txt" "$PACK/mt5/SETUP.txt" "$STAGE/" 2>/dev/null || true
mkdir -p "$STAGE/accounts" "$STAGE/mt4" "$STAGE/mt5"
cp "$PACK/accounts/JM-FX-ACCOUNTS.txt" "$STAGE/accounts/" 2>/dev/null || true
cp "$PACK/mt4/SETUP.txt" "$STAGE/mt4/" 2>/dev/null || true
cp "$PACK/mt5/SETUP.txt" "$STAGE/mt5/" 2>/dev/null || true

mkdir -p "$STAGE/mt5/Experts" "$STAGE/mt4/Experts" "$STAGE/pc-agent" "$STAGE/docs" "$STAGE/python"

echo "==> Copy EAs and agent..."
cp "$ROOT/mt5/Experts/JM_Forex_Bridge.mq5" "$STAGE/mt5/Experts/"
cp "$ROOT/mt4/Experts/JM_Forex_Bridge.mq4" "$STAGE/mt4/Experts/"
cp "$ROOT/scripts/jm_mt5_pc_agent.py" "$STAGE/pc-agent/"
cp "$ROOT/releases/JM-FX-MT5-Bridge-Pack/pc-agent/start-jm-mt5-agent.bat" "$STAGE/pc-agent/legacy-start.bat" 2>/dev/null || true

echo "==> Copy docs..."
for doc in MT5_NO_AGENT_SETUP.md MT4_SETUP.md XM_MT5_SETUP.md VANTAGE_MT4_CHECKLIST.md; do
  if [[ -f "$ROOT/docs/$doc" ]]; then
    cp "$ROOT/docs/$doc" "$STAGE/docs/"
  fi
done

echo "==> Download Python ${PYTHON_VER} embeddable (~10 MB)..."
TMP_PY="$STAGE/.python-dl"
mkdir -p "$TMP_PY"
if [[ ! -f "$TMP_PY/$PYTHON_ZIP" ]]; then
  curl -fsSL "$PYTHON_URL" -o "$TMP_PY/$PYTHON_ZIP"
fi
unzip -qo "$TMP_PY/$PYTHON_ZIP" -d "$STAGE/python"
rm -rf "$TMP_PY"

# Enable site imports on embeddable Python (for pip/extensions if needed later)
PTH=$(find "$STAGE/python" -name 'python*._pth' | head -1)
if [[ -f "$PTH" ]]; then
  if ! grep -q '^import site' "$PTH"; then
    echo 'import site' >> "$PTH"
  fi
fi

echo "==> Write VERSION.txt..."
cat > "$STAGE/VERSION.txt" <<EOF
JM-FX-Complete-Pack
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Python: ${PYTHON_VER} embed-amd64
MT5 EA: v2.00 (cloud bridge)
MT4 EA: v1.00
EOF

echo "==> Create ZIP..."
rm -f "$ZIP"
(cd "$STAGE" && zip -qr "$ZIP" .)

SIZE=$(du -h "$ZIP" | cut -f1)
echo "==> Done: $ZIP ($SIZE)"
rm -rf "$STAGE"
