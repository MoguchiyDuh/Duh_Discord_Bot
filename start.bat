@echo off
title Duh Discord Bot

REM Change to the directory where this script is located
cd /d "%~dp0"

echo Starting Duh Discord Bot...
echo Current directory: %CD%
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ and add it to your PATH
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate

REM Check if requirements.txt exists and install dependencies
if exist "requirements.txt" (
    echo Installing/updating dependencies...
    pip install -r requirements.txt --quiet
) else (
    echo WARNING: requirements.txt not found, skipping dependency installation
)

REM Check if .env file exists
if not exist ".env" (
    echo ERROR: .env file not found
    echo Please create a .env file with your DISCORD_TOKEN and GENIUS_API_KEY
    pause
    exit /b 1
)

echo.
echo Starting bot...
echo Press Ctrl+C to stop the bot
echo.

REM Run the bot
python -m bot

REM Keep window open if bot crashes
if errorlevel 1 (
    echo.
    echo Bot stopped with error code %errorlevel%
    pause
)