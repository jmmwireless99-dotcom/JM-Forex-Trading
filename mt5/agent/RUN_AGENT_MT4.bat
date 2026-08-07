@echo off
setlocal
cd /d "%~dp0"
title JM Forex MT4 Agent
echo ============================================
echo   JM Forex MT4 Agent  (always-on MT4 login)
echo ============================================
echo.
copy /Y "config.mt4.json" "config.json" >nul
echo Starting MT4 agent... keep this window open.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0jm_mt_agent.ps1"
echo.
pause
endlocal
