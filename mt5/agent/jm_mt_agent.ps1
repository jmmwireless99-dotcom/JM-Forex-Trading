# JM Forex Windows MT5 remote agent (PowerShell 5.1+)
# No Python needed. Keep MT5 + JM_Forex_Bridge EA open on XAUUSD.

$ErrorActionPreference = "Continue"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

function Get-JmConfig {
  $cfgPath = Join-Path $Here "config.json"
  $example = Join-Path $Here "config.example.json"
  if (-not (Test-Path $cfgPath)) {
    if (Test-Path $example) {
      Copy-Item $example $cfgPath -Force
      Write-Host "[!] Created config.json from example"
    } else {
      throw "Missing config.json"
    }
  }
  $raw = Get-Content -Path $cfgPath -Raw
  return ($raw | ConvertFrom-Json)
}

function Read-JmFile([string]$FilePath) {
  if (-not (Test-Path $FilePath)) { return "" }
  try {
    return [System.IO.File]::ReadAllText($FilePath)
  } catch {
    return ""
  }
}

function Write-JmFile([string]$FilePath, [string]$Text) {
  $tmp = $FilePath + ".tmp"
  [System.IO.File]::WriteAllText($tmp, $Text)
  Move-Item -LiteralPath $tmp -Destination $FilePath -Force
}

function Invoke-JmApi {
  param(
    [string]$Method,
    [string]$Url,
    [string]$Token,
    $Body = $null
  )
  $headers = @{
    "Accept" = "application/json"
    "X-JM-Bridge-Token" = $Token
    "User-Agent" = "JM-MT-Agent-PS/1.1"
  }
  if ($null -ne $Body) {
    $json = $Body | ConvertTo-Json -Compress -Depth 8
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -ContentType "application/json; charset=utf-8" -Body $json -TimeoutSec 15
  }
  return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -TimeoutSec 15
}

try {
  $cfg = Get-JmConfig
} catch {
  $msg = $_.Exception.Message
  Write-Host ("ERROR loading config: " + $msg)
  exit 1
}

$token = [string]$cfg.bridge_token
if ([string]::IsNullOrWhiteSpace($token) -or $token.StartsWith("PASTE_")) {
  Write-Host "ERROR: set bridge_token in config.json using Notepad."
  Write-Host ("File: " + (Join-Path $Here "config.json"))
  exit 1
}

$api = [string]$cfg.api_base
if ([string]::IsNullOrWhiteSpace($api)) {
  $api = "https://jmtechsolution.cloud/fx/api"
}
$api = $api.TrimEnd("/")

$filesDir = [string]$cfg.files_dir
if ([string]::IsNullOrWhiteSpace($filesDir)) {
  $filesDir = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files"
}

$symbol = [string]$cfg.symbol
if ([string]::IsNullOrWhiteSpace($symbol)) {
  $symbol = "XAUUSD"
}
$symbol = $symbol.ToUpper()

$pollMs = 500
if ($null -ne $cfg.poll_ms) {
  $pollMs = [int]$cfg.poll_ms
}
if ($pollMs -lt 250) { $pollMs = 250 }

$statusF = Join-Path $filesDir "jm_status.csv"
$ticksF = Join-Path $filesDir "jm_ticks.csv"
$positionsF = Join-Path $filesDir "jm_positions.csv"
$commandF = Join-Path $filesDir "jm_command.csv"
$ackF = Join-Path $filesDir "jm_ack.csv"
$hostName = $env:COMPUTERNAME

Write-Host "JM Forex MT5 remote agent (PowerShell)"
Write-Host ("  API     : " + $api)
Write-Host ("  Files   : " + $filesDir)
Write-Host ("  Symbol  : " + $symbol)
Write-Host ("  Host    : " + $hostName)
Write-Host "Keep MT5 open with JM_Forex_Bridge EA. Ctrl+C to stop."
Write-Host "------------------------------------------------------------"

if (-not (Test-Path $filesDir)) {
  Write-Host "WARNING: Common Files folder missing."
  Write-Host "Win+R then paste: %APPDATA%\MetaQuotes\Terminal\Common\Files"
}

$lastCmdId = ""
$lastAck = ""
$okPushes = 0

while ($true) {
  try {
    $statusCsv = Read-JmFile $statusF
    $ticksCsv = Read-JmFile $ticksF
    $positionsCsv = Read-JmFile $positionsF
    $ackCsv = Read-JmFile $ackF

    $clearId = $null
    if (-not [string]::IsNullOrWhiteSpace($ackCsv)) {
      $ackTrim = $ackCsv.Trim()
      if ($ackTrim -ne $lastAck) {
        $lastAck = $ackTrim
        $parts = $ackTrim.Split(",")
        if ($parts.Length -gt 0) {
          $clearId = $parts[0].Trim()
          if ([string]::IsNullOrWhiteSpace($clearId)) { $clearId = $null }
        }
      }
    }

    $pushBody = @{
      status_csv = $statusCsv
      ticks_csv = $ticksCsv
      positions_csv = $positionsCsv
      ack_csv = $ackCsv
      symbol = $symbol
      agent_host = $hostName
    }
    if ($null -ne $clearId) {
      $pushBody["clear_command_id"] = $clearId
    }

    $push = Invoke-JmApi -Method "POST" -Url ($api + "/mt/remote/push") -Token $token -Body $pushBody
    $okPushes = $okPushes + 1
    if (($okPushes -eq 1) -or (($okPushes % 20) -eq 0)) {
      $st = "NO"
      $tk = "NO"
      if (-not [string]::IsNullOrWhiteSpace($statusCsv)) { $st = "yes" }
      if (-not [string]::IsNullOrWhiteSpace($ticksCsv)) { $tk = "yes" }
      $ts = Get-Date -Format "HH:mm:ss"
      $okVal = $push.ok
      Write-Host ("[" + $ts + "] push ok=" + $okVal + " status=" + $st + " ticks=" + $tk)
    }

    $poll = Invoke-JmApi -Method "GET" -Url ($api + "/mt/remote/poll") -Token $token
    if ($null -ne $poll.command) {
      $cmdCsv = [string]$poll.command.csv
      $cmdId = [string]$poll.command.id
      if ((-not [string]::IsNullOrWhiteSpace($cmdCsv)) -and (-not [string]::IsNullOrWhiteSpace($cmdId)) -and ($cmdId -ne $lastCmdId)) {
        Write-JmFile $commandF $cmdCsv
        $lastCmdId = $cmdId
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host ("[" + $ts + "] command -> EA id=" + $cmdId)
      }
    }
  } catch {
    $msg = $_.Exception.Message
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host ("[" + $ts + "] [error] " + $msg)
    Start-Sleep -Seconds 2
  }
  Start-Sleep -Milliseconds $pollMs
}
