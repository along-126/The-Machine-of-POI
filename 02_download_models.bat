@echo off
setlocal
cd /d "%~dp0"
title POI Machine - Download Face Models

echo =====================================================
echo POI Machine - Download face models
echo =====================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python environment is missing.
    echo Run 01_install_environment.bat first.
    goto error_end
)

".venv\Scripts\python.exe" download_models.py
if errorlevel 1 goto failed

echo.
echo [OK] Models downloaded and verified.
echo Future application runs can work offline.
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] Model download failed. Check the messages above.
:error_end
echo.
pause
exit /b 1
