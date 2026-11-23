@echo off
title OwO Discord Bot

:: Pehle bot.py wale folder mein jao
cd /d "%~dp0"

echo ========================================================
echo               OwO Discord Bot Starter
echo ========================================================
echo.

:: Detect Python executable
set "PY_CMD="

:: 1. Check local pythoncore installation
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
    goto :FOUND_PY
)

:: 2. Check standard python in PATH
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :FOUND_PY
)

:: 3. Check py launcher
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=py"
    goto :FOUND_PY
)

echo [!] Python nahi mila! Kripya https://www.python.org se Python install karein aur "Add to PATH" zaroor select karein.
pause
exit /b

:FOUND_PY
echo [*] Using Python: %PY_CMD%
echo [*] Installing / Verifying required libraries...
"%PY_CMD%" -m pip install -r requirements.txt >nul 2>&1

echo.
echo ========================================================
echo             OwO Bot Start Ho Raha Hai...
echo ========================================================
echo.
"%PY_CMD%" bot.py
if %errorlevel% neq 0 (
    echo.
    echo [!] Bot kisi wajah se ruk gaya. Upar error message padhein.
)
pause
