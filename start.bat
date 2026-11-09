@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if /i "%~1"=="--server" goto :server

rem Prefer the packaged standalone build; fall back to a silent pythonw launch.
if exist "%~dp0ACGVault\ACGVault.exe" (
    start "" "%~dp0ACGVault\ACGVault.exe"
    exit /b 0
)

where pythonw >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pythonw.exe not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

start "" pythonw "%~dp0desktop_app.py"
exit /b 0

:server
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python.exe not found.
    pause
    exit /b 1
)
echo Server mode: http://127.0.0.1:8000  (Ctrl+C to stop)
python "%~dp0main.py"
pause
