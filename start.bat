@echo off
chcp 65001 >nul
title Smart QA - Backend
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ================================================
echo   Smart QA Agent - Backend
echo ================================================
echo.

cd /d "%~dp0"

echo [1/4] Checking .env config...
if not exist .env (
    echo   WARNING: .env file not found, creating from .env.example
    copy .env.example .env >nul 2>nul
    echo   Please edit .env with your LLM_API_KEY and other settings
)

echo [2/4] Docker services...
docker compose -f deploy/docker-compose.yml up -d postgres redis milvus 2>nul
if errorlevel 1 (
    echo   Skipped: Docker not available or services already running
) else (
    echo   PostgreSQL + Redis + Milvus started
)

echo [3/4] Database setup...
uv run python -X utf8 -m src.smart_qa.scripts.init_db 2>nul
if errorlevel 1 (
    echo   Skipped: DB init failed (may be already initialized)
) else (
    echo   Database initialized
)

echo [4/4] Starting server...
echo.
echo ================================================
echo   Backend API:    http://localhost:8000
echo   Swagger Docs:   http://localhost:8000/docs
echo   Health Check:   http://localhost:8000/health
echo ================================================
echo.
echo To start the frontend, open another terminal and run:
echo   cd frontend ^&^& npm install ^&^& npm run dev
echo   Frontend: http://localhost:5173
echo.

uv run python -X utf8 -m uvicorn src.smart_qa.web:app --host 0.0.0.0 --port 8000 --reload
pause
