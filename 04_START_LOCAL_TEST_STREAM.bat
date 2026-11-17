@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" local_mjpeg_stream.py
) else (
    py -3.14 local_mjpeg_stream.py
)
echo.
echo If the test stopped, see the message above.
pause
