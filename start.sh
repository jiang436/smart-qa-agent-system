#!/bin/bash
set -e

echo "================================================"
echo "  Smart QA Agent — 一键启动"
echo "================================================"
echo ""

cd "$(dirname "$0")"

# ── 1. 启动基础设施 ──
echo "[1/4] 启动 PostgreSQL + Redis + Milvus..."
if command -v docker &>/dev/null; then
  docker compose -f deploy/docker-compose.yml up -d postgres redis milvus 2>/dev/null && echo "  ✓ 基础设施已启动" || echo "  ! Docker 不可用，请确保 PostgreSQL/Redis/Milvus 已手动运行"
else
  echo "  ! Docker 未安装，请确保 PostgreSQL/Redis/Milvus 已手动运行"
fi

# ── 2. 安装依赖 ──
echo "[2/4] 安装 Python 依赖..."
uv sync --frozen 2>/dev/null || uv sync
echo "  ✓ 依赖已安装"

# ── 3. 初始化 ──
echo "[3/4] 初始化数据库 + 知识库..."
uv run python -m smart_qa.scripts.init_db 2>/dev/null && echo "  ✓ 数据库已初始化" || echo "  ! 数据库初始化失败（可能已初始化）"
uv run python -m smart_qa.scripts.init_vector_store 2>/dev/null && echo "  ✓ 知识库已初始化" || echo "  ! 知识库初始化跳过"

# ── 4. 启动服务 ──
echo "[4/4] 启动 API 服务..."
echo ""
echo "  http://localhost:8000"
echo "  http://localhost:8000/docs  (Swagger)"
echo "  http://localhost:8000/health"
echo ""

uv run smart-qa
