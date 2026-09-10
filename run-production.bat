@echo off
title Guest Posting AI - Production Server
cd /d "%~dp0"

echo ========================================================
echo Guest Posting AI - Unified Production Server Launcher
echo ========================================================
echo.

echo [1/2] Building React Frontend for Production...
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Frontend build failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/2] Launching Unified FastAPI Production Server...
echo App & API will run simultaneously on http://localhost:8000
echo Docs available at http://localhost:8000/docs
echo.

cd /d "%~dp0backend"
set SERVE_FRONTEND=True
set ENVIRONMENT=development
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
