@echo off
setlocal
cd /d "%~dp0"
title JM Forex MT4 Agent — BTCUSD
echo ============================================
echo   JM Forex MT4 Agent  (BTCUSD / Nonoy)
echo   Strategy TF: M5  ·  BTC_EMA_RSI_Scalp
echo ============================================
echo.
copy /Y "config.mt4.btc.json" "config.json" >nul
echo Starting MT4 BTC agent... keep this window open.
echo Attach EA on BTCUSD M5 chart (InpSymbol=BTCUSD).
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0jm_mt_agent.ps1"
echo.
pause
endlocal
