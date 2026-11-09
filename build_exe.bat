@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo [ACG Vault] Building standalone app (onedir, windowed)...
echo.

python -m PyInstaller --noconfirm --clean --onedir --windowed --name ACGVault ^
  --icon "%~dp0static\icon.ico" ^
  --add-data "%~dp0static;static" ^
  --collect-all webview ^
  --collect-submodules uvicorn ^
  --collect-submodules pystray ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  --distpath "%~dp0" ^
  --workpath "%~dp0build" ^
  --specpath "%~dp0build" ^
  "%~dp0desktop_app.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See the log above.
    pause
    exit /b 1
)

echo.
echo Done: %~dp0ACGVault\ACGVault.exe
echo Data folder: %~dp0data (shared with the source build)
pause
