# 部署指南

## 架构概览

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  Vue 3 SPA  │────▶│  FastAPI      │────▶│  PostgreSQL   │
│  (Port 5173)│     │  (Port 8000)  │     │  (Port 5432)  │
└─────────────┘     └──────────────┘     └───────────────┘
                           │               ┌───────────────┐
                           ├──────────────▶│  Redis        │
                           │               │  (Port 6379)  │
                           │               └───────────────┘
                           │               ┌───────────────┐
                           ├──────────────▶│  Milvus       │
                           │               │  (Port 19530) │
                           │               └───────────────┘
                           │               ┌───────────────┐
                           └──────────────▶│  LLM API      │
                                           │  (DeepSeek等)  │
                                           └───────────────┘
```

## 环境变量

复制 `.env.example` 为 `.env`，按需修改：

| 变量 | 说明 | 必填 |
|------|------|------|
| `LLM_API_KEY` | LLM API 密钥 | ✅ |
| `LLM_BASE_URL` | LLM API 地址 | ✅ |
| `LIGHTWEIGHT_MODEL` | 轻量模型名 | — |
| `POSTGRES_DSN` | PostgreSQL 连接串 | — |
| `REDIS_URL` | Redis 连接串 | — |
| `MILVUS_HOST` | Milvus 地址 | — |
| `EMBEDDING_BACKEND` | Embedding 后端 (api/local/ollama) | — |
| `EMBEDDING_FALLBACK_MODEL` | 本地回退模型 (空=禁用) | — |
| `AGENT_TIMEOUT` | Agent 超时秒数 | — |
| `SUPPORT_PHONE` | 售后客服热线 | 推荐 |

## 部署方式

### 方式一：Docker Compose（推荐）

```bash
# 启动全部服务
docker compose -f deploy/docker-compose.yml up -d

# 仅启动基础设施
docker compose -f deploy/docker-compose.yml up -d postgres redis etcd minio milvus
```

**注意**：Milvus 依赖 etcd + minio。如果 etcd 连接失败，可使用 standalone 模式：
```bash
docker run -d --name milvus -p 19530:19530 -p 9091:9091 \
  -e ETCD_USE_EMBED=true -e COMMON_STORAGETYPE=local \
  milvusdb/milvus:v2.5.6 milvus run standalone
```

### 方式二：手动启动

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY 等必要配置

# 3. 初始化数据库
uv run python -m smart_qa.scripts.init_db
uv run alembic upgrade head     # 或通过 Alembic 迁移

# 4. 初始化向量库
uv run python -m smart_qa.scripts.init_vector_store

# 5. 启动后端
uv run smart-qa                 # http://localhost:8000

# 6. 启动前端 (另开终端)
cd frontend
npm install
npm run build                   # 生产构建 → dist/
# 或开发模式:
npm run dev                     # http://localhost:5173
```

### 方式三：Windows 一键启动

```cmd
start.bat
```

前端需手动启动：
```cmd
cd frontend && npm install && npm run dev
```

## 数据库迁移

项目使用 Alembic 管理数据库版本：

```bash
# 应用所有迁移
uv run alembic upgrade head

# 生成新迁移 (修改 ORM 模型后)
uv run alembic revision --autogenerate -m "描述"

# 回滚一个版本
uv run alembic downgrade -1
```

初始迁移 `8f9d8bdcbf2f` 创建全部 6 张业务表。

## 生产注意事项

1. **LLM 配置**：必须设置 `LLM_API_KEY` 和 `LLM_BASE_URL`
2. **Embedding**：生产推荐 `EMBEDDING_BACKEND=api`，避免加载本地模型（可能 crash）
3. **Embedding 回退**：设置 `EMBEDDING_FALLBACK_MODEL=` (空) 禁用本地模型回退
4. **CORS**：修改 `web.py` 中 `allow_origins` 为前端实际域名
5. **故障决策树**：维护 `data/diagnosis_tree.json` 更新排查流程
6. **知识库**：将产品文档放入 `data/knowledge/` 子目录，重启后自动索引
7. **关键词调优**：维护 `data/router_keywords.json` 优化意图分类
8. **可观测**：配置 `OTEL_EXPORTER_OTLP_ENDPOINT` 接入 SigNoz/Grafana
9. **评测**：每次改 Prompt 后运行 `make eval` 验证回归

## 前端生产部署

```bash
cd frontend
npm run build              # 输出到 dist/
# 将 dist/ 部署到 Nginx/CDN，反向代理 /api/v1 到后端 8000 端口
```
