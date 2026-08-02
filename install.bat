@echo off
title Meeting Notes AI - First Time Setup
echo ================================
echo  Meeting Notes AI - Setup
echo ================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

echo.
echo Installing dependencies (this may take a few minutes)...
call venv\Scripts\activate
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Creating desktop shortcut...
powershell -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"

echo.
echo ================================
echo  Setup complete!
echo ================================
echo.
echo Double-click "Meeting Notes AI" on your Desktop to start.
echo Or run run_app.bat directly from this folder.
echo.
pause
