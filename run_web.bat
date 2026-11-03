@echo off
REM MindfulBreath: GDX respiration belt (USB) -> local server -> web UI
cd /d "%~dp0"
python -m pip install -q godirect hidapi bleak
start "" http://localhost:8000
python web\server.py %*
pause
