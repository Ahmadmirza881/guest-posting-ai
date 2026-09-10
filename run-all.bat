@echo off
title Guest Posting AI - Launcher
cd /d "%~dp0"
echo ========================================================
echo Starting Guest Posting AI - Full Application Stack
echo ========================================================
echo.
echo [1/2] Launching FastAPI Backend on http://localhost:8000 ...
start "Guest Posting AI - Backend" cmd /k "cd /d "%~dp0backend" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] Launching Vite Frontend on http://localhost:5173 ...
start "Guest Posting AI - Frontend" cmd /k "cd /d "%~dp0" && npm run dev"

echo.
echo Both servers are starting in separate windows.
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000
echo Docs:     http://localhost:8000/docs
echo.
pause
