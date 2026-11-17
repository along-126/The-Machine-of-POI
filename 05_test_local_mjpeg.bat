@echo off
setlocal
cd /d "%~dp0"
title THE MACHINE - Local MJPEG Stream Check
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Missing .venv Python. Put this file in the active THE MACHINE folder.
  goto :failed
)
".venv\Scripts\python.exe" stream_connection_selftest.py
if errorlevel 1 goto :failed
echo.
echo [PASS] Network MJPEG test succeeded.
pause
exit /b 0
:failed
echo.
echo [ERROR] Test failed. Please send a screenshot of this window.
pause
exit /b 1
