@echo off
REM JM FX MT5 PC Bridge Agent — run on Windows PC with XM MT5 open
title JM FX MT5 Bridge Agent
cd /d "%~dp0.."
where python >nul 2>&1
if %errorlevel%==0 (
  python scripts\jm_mt5_pc_agent.py
) else (
  py -3 scripts\jm_mt5_pc_agent.py
)
pause
