@echo off
cd /d "%~dp0"
set PY=python
if exist "..\.venv\Scripts\python.exe" set PY=..\.venv\Scripts\python.exe
echo Starting Seat Signal on http://localhost:8000 (phones on the same Wi-Fi: http://YOUR-PC-IP:8000) ...
start "" http://localhost:8000
%PY% -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
