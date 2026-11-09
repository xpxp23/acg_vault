@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if exist "%~dp0start_silent.vbs" (
    start "" wscript.exe //B //Nologo "%~dp0start_silent.vbs"
    exit /b 0
)

if exist "%~dp0ACGVault\ACGVault.exe" (
    start "" "%~dp0ACGVault\ACGVault.exe"
    exit /b 0
)

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0desktop_app.py"
    exit /b 0
)

start "" pythonw "%~dp0desktop_app.py"
exit /b 0
