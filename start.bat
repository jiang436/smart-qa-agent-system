@echo off
title Smart QA - Backend
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ================================================
echo   Smart QA Agent - Backend
echo ================================================
echo.

cd /d "%~dp0"

:: ---- 1. Docker (optional) ----
echo [1/3] Docker services...
docker compose -f deploy/docker-compose.yml up -d postgres redis 2>nul
if errorlevel 1 (
    echo   Skipped: Docker not available
) else (
    echo   PostgreSQL + Redis started
)

:: ---- 2. Init DB (optional) ----
echo [2/3] Database setup... (auto-retry in background)
start /b python -X utf8 -m src.scripts.init_db >nul 2>&1

:: ---- 3. Start ----
echo [3/3] Starting server...
echo.
echo ================================================
echo   Backend API:   http://localhost:8000
echo   Swagger Docs:  http://localhost:8000/docs
echo   Health Check:  http://localhost:8000/health
echo.
echo   Test commands:
echo     curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d "{\"user_id\":\"u1\",\"message\":\"你好\"}"
echo ================================================
echo.

python -X utf8 -m uvicorn src.app.web:app --host 0.0.0.0 --port 8000 --reload
pause
