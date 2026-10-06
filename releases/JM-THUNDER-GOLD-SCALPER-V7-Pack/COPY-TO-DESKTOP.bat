@echo off
setlocal EnableExtensions EnableDelayedExpansion
title JM Thunder GOLD Scalper V7.1 - copy to Desktop + MT5 Experts

set "EA=JM_THUNDER_GOLD_SCALPER_V7.mq5"
set "SETUP=SETUP.txt"
set "SRC_EA="
set "SRC_SETUP="

if exist "%~dp0Experts\%EA%" set "SRC_EA=%~dp0Experts\%EA%"
if not defined SRC_EA if exist "%~dp0%EA%" set "SRC_EA=%~dp0%EA%"
if not defined SRC_EA if exist "%~dp0..\mt5\Experts\%EA%" set "SRC_EA=%~dp0..\mt5\Experts\%EA%"

if exist "%~dp0%SETUP%" set "SRC_SETUP=%~dp0%SETUP%"
if not defined SRC_SETUP if exist "%~dp0JM_THUNDER_GOLD_SCALPER_V7_SETUP.txt" set "SRC_SETUP=%~dp0JM_THUNDER_GOLD_SCALPER_V7_SETUP.txt"
if not defined SRC_SETUP if exist "%~dp0..\mt5\JM_THUNDER_GOLD_SCALPER_V7_SETUP.txt" set "SRC_SETUP=%~dp0..\mt5\JM_THUNDER_GOLD_SCALPER_V7_SETUP.txt"

if not defined SRC_EA (
  echo HINDI NAKITA ang %EA%
  pause
  exit /b 1
)

set "DESK=%USERPROFILE%\Desktop"
if not exist "%DESK%" set "DESK=%USERPROFILE%\OneDrive\Desktop"
if not exist "%DESK%" (
  echo Walang Desktop folder.
  pause
  exit /b 1
)

set "OUT=%DESK%\JM-THUNDER-GOLD-SCALPER-V7"
mkdir "%OUT%" 2>nul
copy /Y "%SRC_EA%" "%OUT%\%EA%" >nul
if defined SRC_SETUP copy /Y "%SRC_SETUP%" "%OUT%\SETUP.txt" >nul
copy /Y "%SRC_EA%" "%DESK%\%EA%" >nul

echo OK Desktop folder:
echo   %OUT%\%EA%
echo OK Desktop file:
echo   %DESK%\%EA%
echo.

set "META=%APPDATA%\MetaQuotes\Terminal"
set COPIED=0
if exist "%META%" (
  for /d %%D in ("%META%\*") do (
    if exist "%%D\MQL5\Experts\" if exist "%%D\origin.txt" (
      findstr /i /c:"Vantage" "%%D\origin.txt" >nul 2>nul
      if not errorlevel 1 (
        copy /Y "%SRC_EA%" "%%D\MQL5\Experts\%EA%" >nul
        echo OK Vantage Experts:
        echo   %%D\MQL5\Experts\%EA%
        set /a COPIED+=1
      )
    )
  )
  if !COPIED! EQU 0 (
    for /d %%D in ("%META%\*") do (
      if exist "%%D\MQL5\Experts\" (
        copy /Y "%SRC_EA%" "%%D\MQL5\Experts\%EA%" >nul
        echo OK MT5 Experts:
        echo   %%D\MQL5\Experts\%EA%
        set /a COPIED+=1
      )
    )
  )
)

echo.
echo Next: MetaEditor F7, attach JM_THUNDER_GOLD_SCALPER_V7 sa gold chart.
echo DEMO muna. Algo Trading ON.
pause
endlocal
