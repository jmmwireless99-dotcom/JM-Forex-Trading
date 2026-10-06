@echo off
setlocal EnableExtensions EnableDelayedExpansion
title JM Thunder GOLD Scalper - copy to Vantage MT5 Experts

set "EA=JM_THUNDER_GOLD_SCALPER.mq5"
set "SRC="
if exist "%~dp0Experts\%EA%" set "SRC=%~dp0Experts\%EA%"
if not defined SRC if exist "%~dp0%EA%" set "SRC=%~dp0%EA%"
if not defined SRC if exist "%~dp0..\mt5\Experts\%EA%" set "SRC=%~dp0..\mt5\Experts\%EA%"

if not defined SRC (
  echo HINDI NAKITA ang %EA%
  echo Ilagay ang BAT kasama ang Experts\%EA% folder.
  pause
  exit /b 1
)

set "META=%APPDATA%\MetaQuotes\Terminal"
if not exist "%META%" (
  echo Walang MT5 data folder:
  echo   %META%
  echo Buksan muna ang Vantage MT5 kahit isang beses, tapos ulitin ito.
  pause
  exit /b 1
)

echo Source:
echo   %SRC%
echo.

set COPIED=0

for /d %%D in ("%META%\*") do (
  if exist "%%D\MQL5\Experts\" if exist "%%D\origin.txt" (
    findstr /i /c:"Vantage" "%%D\origin.txt" >nul 2>nul
    if not errorlevel 1 (
      copy /Y "%SRC%" "%%D\MQL5\Experts\%EA%" >nul
      echo OK Vantage Experts:
      echo   %%D\MQL5\Experts\%EA%
      set /a COPIED+=1
    )
  )
)

if !COPIED! EQU 0 (
  echo Walang origin.txt na "Vantage". Kokopyahin sa lahat ng MT5 MQL5\Experts.
  for /d %%D in ("%META%\*") do (
    if exist "%%D\MQL5\Experts\" (
      copy /Y "%SRC%" "%%D\MQL5\Experts\%EA%" >nul
      echo OK:
      echo   %%D\MQL5\Experts\%EA%
      set /a COPIED+=1
    )
  )
)

if !COPIED! EQU 0 (
  echo WALANG MQL5\Experts folder.
  pause
  exit /b 1
)

echo.
echo Tapos. Sa Vantage MT5:
echo   1. Navigator - refresh, o MetaEditor F7
echo   2. Attach sa XAUUSD / XAUUSDm chart ^(isang EA lang^)
echo   3. Algo Trading ON. DEMO muna.
pause
endlocal
