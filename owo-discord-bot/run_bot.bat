@echo off
title OwO Discord Bot

:: Pehle bot.py wale folder mein jao
cd /d "%~dp0"

echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python nahi mila! Kripya https://www.python.org se Python install karein aur "Add to PATH" zaroor select karein.
    pause
    exit /b
)

echo Installing required libraries...
pip install -r requirements.txt

echo.
echo Starting OwO Bot...
echo.
python bot.py
pause
