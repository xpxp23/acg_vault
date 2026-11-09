@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if exist "%~dp0ACGVault\ACGVault.exe" (
    start "" "%~dp0ACGVault\ACGVault.exe"
    exit /b 0
)

start "" pythonw "%~dp0desktop_app.py"
exit /b 0
