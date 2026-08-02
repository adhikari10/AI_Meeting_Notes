@echo off
title Meeting Notes AI
echo Starting Meeting Notes AI...
cd /d "%~dp0"

:: Find Python in venv or system
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe launcher.py
) else if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe launcher.py
) else (
    python launcher.py
)
