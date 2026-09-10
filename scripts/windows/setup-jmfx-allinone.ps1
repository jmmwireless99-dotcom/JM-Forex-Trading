# JM FX All-in-One Windows Setup (Proxmox VM)
# Run as Administrator: powershell -ExecutionPolicy Bypass -File setup-jmfx-allinone.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path "$Root\backend\requirements.txt")) {
    $Root = "C:\jm-forex-trading"
}

Write-Host "JM FX Windows All-in-One Setup"
Write-Host "  Root: $Root"

# --- Python venv ---
$Venv = "$Root\backend\.venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    Write-Host "[1/6] Creating Python venv..."
    python -m venv $Venv
}
Write-Host "[2/6] Installing Python deps..."
& "$Venv\Scripts\pip.exe" install -q -r "$Root\backend\requirements.txt"

# --- Frontend build ---
Write-Host "[3/6] Building frontend (JM_BASE=/fx/)..."
Push-Location "$Root\frontend"
if (-not (Test-Path node_modules)) { npm ci --silent }
$env:JM_BASE = "/fx/"
npm run build
Pop-Location

Write-Host "[4/6] Publishing static assets..."
$Static = "$Root\backend\static"
if (Test-Path $Static) { Remove-Item -Recurse -Force $Static }
New-Item -ItemType Directory -Path $Static | Out-Null
Copy-Item -Recurse "$Root\frontend\dist\*" $Static

# --- Bridge path ---
$User = $env:USERNAME
$BridgeDir = "$env:APPDATA\MetaQuotes\Terminal\Common\Files"
Write-Host "  MT5 bridge dir: $BridgeDir"

# --- .env ---
Write-Host "[5/6] Writing .env..."
$EnvFile = "$Root\.env"
$EnvContent = @"
JM_EXECUTION_MODE=paper
JM_MT5_BRIDGE_DIR=$BridgeDir
JM_MT_SYMBOL=GOLD#
JM_MT5_DEMO_ACCOUNT_CODE=DDDC3D
JM_MT5_DEMO_LOGIN=169250320
JM_MT_REMOTE_BRIDGE=false
JM_DEFAULT_STRATEGY=AI_ML
JM_AUTO_STRATEGY=true
JM_AI_ASSIST=true
JM_AI_GATE_ENTRIES=true
JM_AI_BLOCK_SMC_SELL_OVERLAP=true
JM_ASIA_DESK_ONLY=true
JM_AUTO_FILL_SINGLE_BOOK=false
JM_PAPER_SYNC_LIVE_GOLD=true
JM_STATIC_DIR=$Static
JM_PORTAL_URL=https://jmtechsolution.cloud
"@
Set-Content -Path $EnvFile -Value $EnvContent -Encoding UTF8

# --- DDDC3D account ---
Write-Host "[6/6] Creating DDDC3D account..."
& "$Venv\Scripts\python.exe" "$Root\scripts\create_xm_mt5_demo_account.py" --code DDDC3D --label "XM MT5 Demo Proxmox"

Write-Host ""
Write-Host "OK — next steps:"
Write-Host "  1. Install MT5 + attach JM_Forex_Bridge (InpUseCloudBridge=false)"
Write-Host "  2. Run: powershell -File $Root\scripts\windows\install-jmfx-service.ps1"
Write-Host "  3. Setup Caddy: copy deploy\Caddyfile.windows → C:\Caddy\Caddyfile"
Write-Host "  4. Point DNS jmtechsolution.cloud → this VM public IP"
Write-Host "  5. Open https://jmtechsolution.cloud/fx/"
