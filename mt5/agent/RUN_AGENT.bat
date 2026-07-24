@echo off
setlocal
cd /d "%~dp0"
title JM Forex MT5 Agent
echo ============================================
echo   JM Forex MT5 Agent  (PowerShell)
echo   Walang Python kailangan
echo ============================================
echo.

if not exist "config.json" (
  if exist "config.example.json" (
    copy /Y "config.example.json" "config.json" >nul
    echo [+] Ginawa ang config.json
  )
)

echo Starting agent...
echo Huwag isara ang window na ito.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0jm_mt_agent.ps1"
set ERR=%ERRORLEVEL%

echo.
if not "%ERR%"=="0" (
  echo Agent stopped with error code %ERR%
) else (
  echo Agent exited.
)
echo.
echo --------------------------------------------
echo Pindutin ang kahit anong key para isara...
pause >nul
endlocal
