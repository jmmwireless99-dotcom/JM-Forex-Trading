@echo off
REM JM FX MT5 PC Bridge Agent — uses bundled Python if system Python missing
title JM FX MT5 Bridge Agent
cd /d "%~dp0"

echo.
echo  JM FX MT5 Bridge Agent
echo  ======================
echo  Cloud: https://jmtechsolution.cloud/fx/
echo  Keep this window OPEN while MT5 + EA are running.
echo.

set "PY="
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"

if not defined PY (
  echo  ERROR: Walang Python. I-run muna ang install-python.bat
  echo  O i-double-click ang install-python.bat sa folder na ito.
  pause
  exit /b 1
)

"%PY%" "%~dp0pc-agent\jm_mt5_pc_agent.py" %*
if errorlevel 1 (
  echo.
  echo  Agent error. Check MT5 is open and EA attached on GOLD#.
)
echo.
pause
