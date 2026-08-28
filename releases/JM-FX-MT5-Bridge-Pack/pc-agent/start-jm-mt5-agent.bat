@echo off
REM JM FX MT5 PC Bridge Agent — save this .bat next to jm_mt5_pc_agent.py
title JM FX MT5 Bridge Agent
cd /d "%~dp0"
where python >nul 2>&1
if %errorlevel%==0 (
  python jm_mt5_pc_agent.py
) else (
  py -3 jm_mt5_pc_agent.py
)
pause
