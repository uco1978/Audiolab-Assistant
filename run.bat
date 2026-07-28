@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Product Page Creator - Local Edition

echo.
echo  Product Page Creator - LOCAL EDITION
echo  Ollama only - no cloud API keys
echo.

:: AMD iGPU hint for this session
set OLLAMA_IGPU_ENABLE=1

where python >nul 2>&1 || (echo ERROR: Install Python 3.11+ & pause & exit /b 1)
where npm >nul 2>&1 || (echo ERROR: Install Node.js & pause & exit /b 1)
where ollama >nul 2>&1 || (echo ERROR: Install Ollama from https://ollama.com & pause & exit /b 1)

if not exist ".env" copy /Y ".env.example" ".env" >nul

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)
call ".venv\Scripts\activate.bat"
pip install -q -r backend\requirements.txt

if not exist "%USERPROFILE%\.cache\ms-playwright" (
    echo Installing Playwright browser...
    playwright install chromium
)

if not exist "frontend\node_modules" (
    echo Installing frontend...
    pushd frontend && call npm install && popd
)

echo Checking Ollama...
ollama list >nul 2>&1 || (echo ERROR: Start Ollama app first & pause & exit /b 1)

echo Pulling local models if missing...
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5vl:7b

start "PPC Local - Backend" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && cd backend && echo API http://localhost:8001 && python -m uvicorn app.main:app --port 8001"

start "PPC Local - Worker" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && cd backend && python -m app.worker"

timeout /t 3 /nobreak >nul

start "PPC Local - Frontend" cmd /k "cd /d "%~dp0frontend" && echo UI http://localhost:5174 && npm run dev"

timeout /t 5 /nobreak >nul
start "" "http://localhost:5174"

echo.
echo  Running! http://localhost:5174
echo  See SETUP-AMD.md for Radeon 890M GPU tuning.
echo.
timeout /t 4 /nobreak >nul
