@echo off
REM JM FX MT5 PC Bridge Agent — double-click to start sync
title JM FX MT5 Bridge Agent (GOLD#)
cd /d "%~dp0"

echo.
echo  JM FX MT5 Bridge Agent
echo  ======================
echo  Symbol: GOLD#  |  Poll: 120ms  |  Sync: 800ms
echo  Cloud:  https://jmtechsolution.cloud/fx/
echo.
echo  REQUIREMENTS:
echo   1. MT5 open + logged in (169250320)
echo   2. JM_Forex_Bridge attached on GOLD# chart
echo   3. Algo Trading ON (green)
echo.
echo  Keep this window OPEN while trading.
echo.

where python >nul 2>&1
if %errorlevel%==0 (
  python jm_mt5_pc_agent.py
) else (
  py -3 jm_mt5_pc_agent.py
)

echo.
echo Agent stopped. Press any key to close...
pause >nul
