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
  # Important: no UTF-8 BOM — MT5 EA expects ANSI/plain text CSV
  $enc = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($tmp, $Text, $enc)
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

$platform = [string]$cfg.platform
if ([string]::IsNullOrWhiteSpace($platform)) { $platform = "mt5" }
$platform = $platform.ToLower()
if (($platform -ne "mt4") -and ($platform -ne "mt5")) { $platform = "mt5" }

$prefix = [string]$cfg.file_prefix
if ([string]::IsNullOrWhiteSpace($prefix)) {
  if ($platform -eq "mt4") { $prefix = "jm4_" } else { $prefix = "jm_" }
}

$statusF = Join-Path $filesDir ($prefix + "status.csv")
$ticksF = Join-Path $filesDir ($prefix + "ticks.csv")
$positionsF = Join-Path $filesDir ($prefix + "positions.csv")
$historyF = Join-Path $filesDir ($prefix + "history.csv")
$commandF = Join-Path $filesDir ($prefix + "command.csv")
$ackF = Join-Path $filesDir ($prefix + "ack.csv")
$hostName = $env:COMPUTERNAME

Write-Host ("JM Forex " + $platform.ToUpper() + " remote agent (PowerShell)")
Write-Host ("  API      : " + $api)
Write-Host ("  Platform : " + $platform)
Write-Host ("  Prefix   : " + $prefix)
Write-Host ("  Files    : " + $filesDir)
Write-Host ("  Symbol   : " + $symbol)
Write-Host ("  Host     : " + $hostName)
Write-Host ("Keep " + $platform.ToUpper() + " open with JM_Forex_Bridge EA. Ctrl+C to stop.")
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
    $historyCsv = Read-JmFile $historyF
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
      history_csv = $historyCsv
      ack_csv = $ackCsv
      symbol = $symbol
      agent_host = $hostName
      platform = $platform
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
      $loginVal = $push.mt_login
      Write-Host ("[" + $ts + "] " + $platform + " push ok=" + $okVal + " status=" + $st + " ticks=" + $tk + " login=" + $loginVal)
    }

    # Prefer command piggybacked on push response (more reliable than separate poll)
    $cmdObj = $null
    if ($null -ne $push.command) {
      $cmdObj = $push.command
    } else {
      $poll = Invoke-JmApi -Method "GET" -Url ($api + "/mt/remote/poll?platform=" + $platform) -Token $token
      if ($null -ne $poll.command) { $cmdObj = $poll.command }
    }

    if ($null -ne $cmdObj) {
      $cmdCsv = [string]$cmdObj.csv
      $cmdId = [string]$cmdObj.id
      if ((-not [string]::IsNullOrWhiteSpace($cmdCsv)) -and (-not [string]::IsNullOrWhiteSpace($cmdId)) -and ($cmdId -ne $lastCmdId)) {
        Write-JmFile $commandF $cmdCsv
        $lastCmdId = $cmdId
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host ("[" + $ts + "] " + $platform + " command -> EA id=" + $cmdId)
        # Give EA a moment to ack, then push immediately so cloud does not wait a full poll.
        Start-Sleep -Milliseconds 350
        try {
          $ackCsv2 = Read-JmFile $ackF
          $pushBody2 = @{
            status_csv = (Read-JmFile $statusF)
            ticks_csv = (Read-JmFile $ticksF)
            positions_csv = (Read-JmFile $positionsF)
            history_csv = (Read-JmFile $historyF)
            ack_csv = $ackCsv2
            symbol = $symbol
            agent_host = $hostName
            platform = $platform
          }
          if (-not [string]::IsNullOrWhiteSpace($ackCsv2)) {
            $ackParts = $ackCsv2.Trim().Split(",")
            if ($ackParts.Length -gt 0 -and -not [string]::IsNullOrWhiteSpace($ackParts[0])) {
              $pushBody2["clear_command_id"] = $ackParts[0].Trim()
            }
          }
          $null = Invoke-JmApi -Method "POST" -Url ($api + "/mt/remote/push") -Token $token -Body $pushBody2
        } catch {
          # next loop will retry
        }
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
