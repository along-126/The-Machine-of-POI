@echo off
setlocal
cd /d "%~dp0"
title POI Machine - Install Python Environment

echo =====================================================
echo POI Machine - First-time setup
echo =====================================================
echo.

where py >nul 2>&1
if errorlevel 1 goto no_launcher

py -3.14 --version >nul 2>&1
if errorlevel 1 goto no_python312

if not exist ".venv\Scripts\python.exe" (
    py -3.14 -m venv .venv
    if errorlevel 1 goto failed
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo [OK] Python packages installed.
echo Next: double-click 02_download_models.bat.
echo.
pause
exit /b 0

:no_launcher
echo [ERROR] Python Launcher "py" was not found.
echo Install Python 3.14 x64 from https://www.python.org/downloads/.
echo During installation, enable the Python Launcher option.
goto error_end

:no_python312
echo [ERROR] Python 3.14 was not found.
echo Install Python 3.14 x64 from https://www.python.org/downloads/.
echo Then run this file again.
goto error_end

:failed
echo.
echo [ERROR] Setup failed. Keep this window open and send a screenshot.
:error_end
echo.
pause
exit /b 1
