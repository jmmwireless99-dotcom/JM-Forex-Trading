# JM Forex — Windows MT5 remote agent (PowerShell, no Python needed)
# Keep MT5 open with JM_Forex_Bridge EA on XAUUSD (UseCommonFolder=true)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

function Load-Config {
  $cfgPath = Join-Path $Here "config.json"
  $example = Join-Path $Here "config.example.json"
  if (-not (Test-Path $cfgPath)) {
    if (Test-Path $example) {
      Copy-Item $example $cfgPath -Force
      Write-Host "[!] Created config.json — edit bridge_token if needed"
    } else {
      throw "Missing config.json"
    }
  }
  $raw = Get-Content $cfgPath -Raw -Encoding UTF8
  return $raw | ConvertFrom-Json
}

function Read-Text([string]$Path) {
  if (-not (Test-Path $Path)) { return "" }
  try {
    return [System.IO.File]::ReadAllText($Path)
  } catch {
    return ""
  }
}

function Write-Text([string]$Path, [string]$Text) {
  $tmp = "$Path.tmp"
  [System.IO.File]::WriteAllText($tmp, $Text)
  Move-Item -Force $tmp $Path
}

function Invoke-JmApi([string]$Method, [string]$Url, [string]$Token, $Body = $null) {
  $headers = @{
    "Accept" = "application/json"
    "X-JM-Bridge-Token" = $Token
    "User-Agent" = "JM-MT-Agent-PS/1.0"
  }
  if ($null -ne $Body) {
    $json = $Body | ConvertTo-Json -Compress -Depth 6
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -ContentType "application/json" -Body $json -TimeoutSec 15
  }
  return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -TimeoutSec 15
}

$cfg = Load-Config
$token = [string]$cfg.bridge_token
if ([string]::IsNullOrWhiteSpace($token) -or $token.StartsWith("PASTE_")) {
  Write-Host "ERROR: set bridge_token in config.json (Notepad), NOT in this window."
  Write-Host "File: $(Join-Path $Here 'config.json')"
  exit 1
}

$api = ([string]$cfg.api_base).TrimEnd("/")
if ([string]::IsNullOrWhiteSpace($api)) {
  $api = "https://jmtechsolution.cloud/fx/api"
}

$filesDir = [string]$cfg.files_dir
if ([string]::IsNullOrWhiteSpace($filesDir)) {
  $filesDir = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files"
}
$symbol = if ([string]::IsNullOrWhiteSpace([string]$cfg.symbol)) { "XAUUSD" } else { ([string]$cfg.symbol).ToUpper() }
$pollMs = 500
if ($cfg.poll_ms) { $pollMs = [int]$cfg.poll_ms }
if ($pollMs -lt 250) { $pollMs = 250 }

$statusF = Join-Path $filesDir "jm_status.csv"
$ticksF = Join-Path $filesDir "jm_ticks.csv"
$positionsF = Join-Path $filesDir "jm_positions.csv"
$commandF = Join-Path $filesDir "jm_command.csv"
$ackF = Join-Path $filesDir "jm_ack.csv"
$hostName = $env:COMPUTERNAME

Write-Host "JM Forex MT5 remote agent (PowerShell)"
Write-Host "  API     : $api"
Write-Host "  Files   : $filesDir"
Write-Host "  Symbol  : $symbol"
Write-Host "  Host    : $hostName"
Write-Host "Keep MT5 open with JM_Forex_Bridge EA. Ctrl+C to stop."
Write-Host ("-" * 60)

if (-not (Test-Path $filesDir)) {
  Write-Host "WARNING: folder missing. Win+R paste:"
  Write-Host "  %APPDATA%\MetaQuotes\Terminal\Common\Files"
}

$lastCmdId = ""
$lastAck = ""
$okPushes = 0

while ($true) {
  try {
    $statusCsv = Read-Text $statusF
    $ticksCsv = Read-Text $ticksF
    $positionsCsv = Read-Text $positionsF
    $ackCsv = Read-Text $ackF

    $clearId = $null
    if ($ackCsv -and ($ackCsv.Trim() -ne $lastAck)) {
      $lastAck = $ackCsv.Trim()
      $clearId = ($lastAck.Split(",")[0]).Trim()
      if ([string]::IsNullOrWhiteSpace($clearId)) { $clearId = $null }
    }

    $pushBody = @{
      status_csv = $statusCsv
      ticks_csv = $ticksCsv
      positions_csv = $positionsCsv
      ack_csv = $ackCsv
      symbol = $symbol
      agent_host = $hostName
      clear_command_id = $clearId
    }
    $push = Invoke-JmApi "POST" "$api/mt/remote/push" $token $pushBody
    $okPushes++
    if ($okPushes -eq 1 -or ($okPushes % 20 -eq 0)) {
      $st = if ($statusCsv) { "yes" } else { "NO" }
      $tk = if ($ticksCsv) { "yes" } else { "NO" }
      $ts = Get-Date -Format "HH:mm:ss"
      Write-Host "[$ts] push ok=$($push.ok) status=$st ticks=$tk"
    }

    $poll = Invoke-JmApi "GET" "$api/mt/remote/poll" $token
    if ($poll.command -and $poll.command.csv) {
      $cmdId = [string]$poll.command.id
      if ($cmdId -and ($cmdId -ne $lastCmdId)) {
        Write-Text $commandF ([string]$poll.command.csv)
        $lastCmdId = $cmdId
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host "[$ts] command -> EA id=$cmdId"
      }
    }
  }
  catch {
    Write-Host "[error] $($_.Exception.Message)"
    Start-Sleep -Seconds 2
  }
  Start-Sleep -Milliseconds $pollMs
}
