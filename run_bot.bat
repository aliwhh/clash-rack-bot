@echo off
title Clash Rack Rental Telegram Bot
echo ==============================================
echo   ⚡️ CLASH RACK RENTAL BOT IS STARTING...
echo ==============================================
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
    .\.venv\Scripts\python.exe -m bot.main
) else (
    python -m bot.main
)
pause
