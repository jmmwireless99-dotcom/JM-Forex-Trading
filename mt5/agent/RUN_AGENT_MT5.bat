@echo off
setlocal
cd /d "%~dp0"
title JM Forex MT5 Agent
echo ============================================
echo   JM Forex MT5 Agent  (always-on for Joel)
echo ============================================
echo.
copy /Y "config.mt5.json" "config.json" >nul
echo Starting MT5 agent... keep this window open.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0jm_mt_agent.ps1"
echo.
pause
endlocal
