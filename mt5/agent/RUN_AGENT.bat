@echo off
setlocal
cd /d "%~dp0"
title JM Forex MT5 Agent
echo ============================================
echo   JM Forex MT5 Agent
echo ============================================
echo.

if not exist "config.json" (
  echo [!] Walang config.json
  if exist "config.example.json" (
    copy /Y "config.example.json" "config.json" >nul
    echo [+] Ginawa ang config.json mula sa example.
    echo     Buksan ang config.json sa Notepad at ilagay ang bridge_token.
    echo.
    notepad config.json
    echo.
    echo Pagkatapos mag-Save sa Notepad, pindutin ang kahit anong key dito...
    pause >nul
  ) else (
    echo ERROR: missing config.example.json
    goto end
  )
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  echo Using: py -3
  py -3 jm_mt_agent.py
  set ERR=%ERRORLEVEL%
) else (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 (
    echo Using: python
    python jm_mt_agent.py
    set ERR=%ERRORLEVEL%
  ) else (
    echo.
    echo ERROR: Walang Python sa PC.
    echo Install: https://www.python.org/downloads/
    echo IMPORTANT: check "Add python.exe to PATH"
    echo Tapos i-run ulit ang RUN_AGENT.bat
    set ERR=1
    goto end
  )
)

echo.
if not "%ERR%"=="0" (
  echo Agent stopped with error code %ERR%
) else (
  echo Agent exited normally.
)

:end
echo.
echo --------------------------------------------
echo Window stays open so you can read the error.
pause
endlocal
