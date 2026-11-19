@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Python 3 is required.
  pause
  exit /b 1
)
set PORT=10000
echo Open http://localhost:10000 in your browser.
py server.py
pause
