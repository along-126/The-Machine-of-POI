@echo off
setlocal
cd /d "%~dp0"
title POI Machine - The Machine Visualizer

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python environment is missing.
    echo Run 01_install_environment.bat first.
    goto error_end
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo [ERROR] The application stopped with an error.
echo Keep this window open and send a screenshot of the error.
:error_end
echo.
pause
exit /b 1
