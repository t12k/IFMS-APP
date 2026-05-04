@echo off
title IFMS App
cd /d "%~dp0"
echo ============================================
echo   IFMS - Intelligent Financial Management
echo ============================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting server...
echo.
start /b python -m uvicorn ifms.main:app --port 8000
echo Waiting for server to be ready...
timeout /t 6 /nobreak > nul
echo Opening app in browser...
start "" "http://localhost:8000"
echo.
echo DO NOT CLOSE THIS WINDOW
echo.
python -m uvicorn ifms.main:app --reload --port 8000
pause