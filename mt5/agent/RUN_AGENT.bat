@echo off
cd /d "%~dp0"
echo JM Forex MT5 Agent
echo.
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 jm_mt_agent.py
) else (
  python jm_mt_agent.py
)
pause
