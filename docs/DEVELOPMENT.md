# 开发指南

## 环境要求

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (pip install uv)
- Docker Desktop
- Node.js >= 18 (前端开发)

## 快速启动

### 后端

```bash
# 一键启动 (Windows)
start.bat

# 或手动
uv sync
docker compose -f deploy/docker-compose.yml up -d postgres redis
uv run python -m app.scripts.init_db
uv run python -m app.scripts.init_vector_store
uv run python -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## 目录说明

| 目录 | 用途 |
|------|------|
| `app/` | 后端源码 |
| `frontend/` | Vue 3 前端 |
| `deploy/` | Docker Compose + Dockerfile + 环境变量模板 |
| `docs/` | 项目文档 |
| `tests/` | 测试 |
| `data/knowledge/` | 知识库 Markdown 文档 |

## 常用命令

```bash
# 测试
uv run pytest -v

# Lint (如果安装了 ruff)
uv run ruff check app/

# 添加依赖
uv add <package>
uv add --dev <package>

# API 文档
# 启动后端后访问 http://localhost:8000/docs
```

## 配置说明

`.env` 文件核心配置项:

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API Key | - |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `LIGHTWEIGHT_MODEL` | 轻量模型 | `deepseek-chat` |
| `POSTGRES_DSN` | PostgreSQL 连接 | `postgresql+asyncpg://user:password@localhost:5432/agent` |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6379/0` |
| `MILVUS_HOST` | Milvus 地址 | `localhost` |
| `CACHE_SIMILARITY_THRESHOLD` | 缓存相似度阈值 | `0.95` |
| `MAX_AGENT_STEPS` | Agent 最大步数 | `15` |

## 添加新场景

1. `app/services/` 新建 Service 类
2. `app/scenarios/` 新建 Scenario 类
3. `app/agent/graph.py` 注册节点和边
4. `app/agent/router_agent.py` 添加意图关键词
5. `app/agent/state.py` 如有新状态字段需添加

## Debug

```bash
# 测试 LLM 连接
python -X utf8 -c "from app.core.dependencies import get_llm_client; llm=get_llm_client(); print(llm.invoke('hi').content)"

# 测试知识检索
python -X utf8 -c "
from app.knowledge.retriever import MultiLayerRetriever
r = MultiLayerRetriever()
print(r.retrieve('怎么设置定时清扫'))
"

# 在 Swagger UI 直接测试
# http://localhost:8000/docs
```
