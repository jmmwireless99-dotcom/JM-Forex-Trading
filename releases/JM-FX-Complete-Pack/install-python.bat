@echo off
title JM FX — Python Installer
cd /d "%~dp0"

echo.
echo  JM FX Python Installer
echo  ======================
echo.

where python >nul 2>&1
if %errorlevel%==0 (
  python --version
  echo.
  echo  Python OK na — pwede i-run ang start-jm-mt5-agent.bat
  pause
  exit /b 0
)

echo  Walang Python. I-download at i-install ang Python 3.12...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-python.ps1"
if %errorlevel% neq 0 (
  echo.
  echo  PowerShell install failed. Manual download:
  echo  https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe
  echo.
  echo  O gamitin ang bundled python\ folder sa pack na ito.
  pause
  exit /b 1
)

pause
