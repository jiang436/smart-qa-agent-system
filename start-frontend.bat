@echo off
title Smart QA - Frontend

echo ================================================
echo   Smart QA Agent - Frontend
echo ================================================
echo.

cd /d "%~dp0\frontend"

if not exist "node_modules" (
    echo Installing dependencies...
    npm install
) else (
    echo Dependencies ready
)

echo.
echo ================================================
echo   Frontend:  http://localhost:5173
echo   Backend:   http://localhost:8000
echo ================================================
echo.

npm run dev
pause
