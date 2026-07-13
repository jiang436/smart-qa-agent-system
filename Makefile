# Makefile — Smart QA Agent 常用操作

.PHONY: install dev test lint eval docker-up docker-build docker-down clean

# ── 依赖管理 ──

install:
	uv sync

update:
	uv sync --upgrade

# ── 开发 ──

dev:
	uv run smart-qa

dev-frontend:
	cd frontend && npm run dev

# ── 测试 ──

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=smart_qa --cov-report=term-missing

# ── 代码质量 ──

lint:
	uv run ruff check src/smart_qa/

lint-fix:
	uv run ruff check --fix src/smart_qa/

# ── 评测 ──

eval:
	uv run python -m smart_qa.evaluation.runner

eval-easy:
	uv run python -m smart_qa.evaluation.runner --difficulty easy

# ── 数据库 ──

db-init:
	uv run python -m smart_qa.scripts.init_db

vector-init:
	uv run python -m smart_qa.scripts.init_vector_store

# ── Docker ──

docker-up:
	docker compose -f deploy/docker-compose.yml up -d

docker-up-infra:
	docker compose -f deploy/docker-compose.yml up -d postgres redis milvus

docker-build:
	docker compose -f deploy/docker-compose.yml build web

docker-down:
	docker compose -f deploy/docker-compose.yml down

docker-logs:
	docker compose -f deploy/docker-compose.yml logs -f web

# ── 清理 ──

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv/ .ruff_cache/
