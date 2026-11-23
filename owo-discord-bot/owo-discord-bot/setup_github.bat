@echo off
title Push OwO Bot to GitHub
cd /d "%~dp0"

echo ========================================================
echo        OwO Discord Bot - GitHub Setup & Push
echo ========================================================
echo.

where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Git install nahi hai!
    echo Kripya Git download karein: https://git-scm.com/downloads
    echo Download aur install karne ke baad is script ko dobara chalayein.
    echo.
    pause
    exit /b
)

if not exist ".git" (
    echo [*] Git repository initialize kar rahe hain...
    git init
    git branch -M main
)

echo [*] Files stage kar rahe hain (.env aur database exclude ho jayenge)...
git add bot.py requirements.txt README.md run_bot.bat .gitignore setup_github.bat

git commit -m "Add full OwO Bot with animations (Coinflip, Roulette, Slots, Spin&Win)"

echo.
set /p REPO_URL="Apne GitHub repository ka URL daalein (e.g., https://github.com/username/owo-discord-bot.git): "

if "%REPO_URL%"=="" (
    echo [!] URL nahi diya gaya. Push cancel ho gaya.
    pause
    exit /b
)

git remote remove origin >nul 2>&1
git remote add origin %REPO_URL%

echo.
echo [*] GitHub par push kar rahe hain...
git push -u origin main

echo.
echo ========================================================
echo  Kaam ho gaya! Aapka bot GitHub par upload ho chuka hai!
echo ========================================================
pause
