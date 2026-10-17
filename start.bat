@echo off
chcp 65001 >nul 2>&1
title ACG Game Vault v2.2
cd /d "%~dp0"

echo [1/2] Checking Python environment...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

echo [2/2] Starting ACG Game Vault v2.2 ...
if "%1"=="--server" (
    python main.py
) else (
    python desktop_app.py
)
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited unexpectedly.
    pause
)
