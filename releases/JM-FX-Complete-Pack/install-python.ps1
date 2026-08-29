# JM FX — Download and install Python 3.12 for Windows (PC agent)
# Run: powershell -ExecutionPolicy Bypass -File install-python.ps1

$ErrorActionPreference = "Stop"
$PythonVersion = "3.12.7"
$InstallerName = "python-$PythonVersion-amd64.exe"
$InstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/$InstallerName"
$TempDir = Join-Path $env:TEMP "jmfx-python-install"
$InstallerPath = Join-Path $TempDir $InstallerName

Write-Host ""
Write-Host " JM FX Python Installer"
Write-Host " ======================"
Write-Host ""

if (Get-Command python -ErrorAction SilentlyContinue) {
    $ver = python --version 2>&1
    Write-Host " Python already installed: $ver"
    Write-Host " OK — pwede mo nang i-run ang start-jm-mt5-agent.bat"
    exit 0
}

New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

Write-Host " Downloading Python $PythonVersion ..."
Invoke-WebRequest -Uri $InstallerUrl -OutFile $InstallerPath -UseBasicParsing

Write-Host " Installing (Add to PATH, current user) ..."
$args = @(
    "/quiet",
    "InstallAllUsers=0",
    "PrependPath=1",
    "Include_pip=1",
    "Include_launcher=1"
)
Start-Process -FilePath $InstallerPath -ArgumentList $args -Wait

Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue

Write-Host ""
Write-Host " Done! Buksan ang NEW Command Prompt, then run start-jm-mt5-agent.bat"
Write-Host ""
