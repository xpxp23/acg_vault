@echo off
title ACG Game Vault
cd /d "%~dp0"

echo [1/2] Checking Python environment...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

echo [2/2] Starting ACG Game Vault on http://127.0.0.1:8000 ...
python main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited unexpectedly.
    pause
)
