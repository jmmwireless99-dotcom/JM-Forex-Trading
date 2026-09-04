# Install JM FX backend as Windows service (NSSM)
# Run as Administrator

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path "$Root\backend\requirements.txt")) {
    $Root = "C:\jm-forex-trading"
}

$Nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
if (-not $Nssm) {
    Write-Error "NSSM not found. Run: winget install NSSM.NSSM"
}

$ServiceName = "JMForex"
$Python = "$Root\backend\.venv\Scripts\uvicorn.exe"
$Args = "app.main:app --host 127.0.0.1 --port 8000"
$WorkDir = "$Root\backend"

# Remove old service if exists
& $Nssm stop $ServiceName 2>$null
& $Nssm remove $ServiceName confirm 2>$null

& $Nssm install $ServiceName $Python $Args
& $Nssm set $ServiceName AppDirectory $WorkDir
& $Nssm set $ServiceName AppEnvironmentExtra "JM_STATIC_DIR=$Root\backend\static"
& $Nssm set $ServiceName DisplayName "JM Forex Trading Engine"
& $Nssm set $ServiceName Description "JM FX AI desk + MT5 bridge (DDDC3D)"
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm start $ServiceName

Start-Sleep -Seconds 3
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 5
    Write-Host "Service OK:" ($health | ConvertTo-Json -Compress)
} catch {
    Write-Warning "Service started but health check failed — check MT5 later"
}

Write-Host "JMForex service installed and started."
