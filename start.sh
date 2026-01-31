#!/bin/bash
set -e
export PYTHONUTF8=1

echo "================================================"
echo "  Smart QA Agent - Backend"
echo "================================================"
echo ""

cd "$(dirname "$0")"

# Docker (optional)
echo "[1/3] Docker services..."
docker compose -f deploy/docker-compose.yml up -d postgres redis 2>/dev/null && echo "  OK" || echo "  Skipped"

# Init DB (optional)
echo "[2/3] Database setup..."
python -X utf8 -m src.scripts.init_db 2>/dev/null && echo "  OK" || echo "  Skipped"

# Start
echo "[3/3] Starting server..."
echo ""
echo "  Backend:   http://localhost:8000"
echo "  Swagger:   http://localhost:8000/docs"
echo ""

python -X utf8 -m uvicorn src.app.web:app --host 0.0.0.0 --port 8000 --reload
