@echo off
title Guest Posting AI - Backend API
cd /d "%~dp0backend"
echo ========================================================
echo Starting Guest Posting AI Backend (FastAPI)
echo API URL: http://localhost:8000
echo Docs:    http://localhost:8000/docs
echo ========================================================
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
