# 开发指南

## 环境要求

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose（基础设施用）
- Node.js >= 18（前端开发）

## 快速启动

```bash
# 一键启动 (Unix)
bash start.sh

# 或分步手动
make install            # 安装依赖
make docker-up-infra    # 启动 PostgreSQL + Redis + Milvus
make db-init            # 初始化数据库表
make db-migrate         # 执行 Alembic 迁移
make vector-init        # 初始化向量知识库
make dev                # 启动后端 http://localhost:8000

# 前端 (另一个终端)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## 项目结构

```
smart-qa-agent-system/
├── src/smart_qa/           # 后端源码
│   ├── web.py              # FastAPI 入口 + 生命周期 + DI注册
│   ├── config.py           # pydantic-settings (36项配置)
│   ├── di.py               # 统一依赖注入容器
│   ├── deps.py             # 依赖访问器 (容器代理 + 回退)
│   ├── exceptions.py       # 4层异常体系
│   ├── agent/              # LangGraph 编排
│   │   ├── graph.py        # 9节点状态图 + memory_reader/writer
│   │   ├── state.py        # AgentState TypedDict
│   │   ├── persona.py      # 统一人设 + 越界检测
│   │   ├── agents/         # Agent 节点: Router / RAG / Reflection
│   │   ├── guards/         # LoopDetector 三重防循环
│   │   └── prompts/        # CoT 提示模板 + 加载器
│   ├── api/                # FastAPI 路由
│   │   ├── routes/         # chat / approval / session / knowledge
│   │   └── stream_handler.py  # SSE 流式处理
│   ├── scenarios/          # 业务场景: QA / 故障 / 耗材 / 设备 / SQL / 报告
│   ├── rag/                # 检索增强生成
│   │   ├── retrieval.py        # MultiLayerRetriever 四层召回
│   │   ├── retrieval_utils.py  # 停用词 + BM25加载工具
│   │   ├── reranker.py         # Cross-Encoder / LLM / 启发式
│   │   ├── chunking.py         # 智能文档分片 (4种策略)
│   │   ├── citation.py         # 引用标注 + 幻觉防护
│   │   └── hyde.py             # HyDE 假设文档嵌入
│   ├── knowledge/           # 知识库
│   │   ├── bm25.py             # 自建BM25倒排索引
│   │   ├── vector_store.py     # Embedding模型单例
│   │   ├── embedding_backends.py  # 可插拔后端 (Local/Ollama/API/Fallback)
│   │   ├── document_parser.py  # PDF/MD/TXT解析
│   │   └── knowledge_graph.py  # 设备兼容图 + GraphRAG
│   ├── memory/              # 记忆系统
│   │   ├── cache.py            # 语义缓存 (Redis + 本地LRU)
│   │   ├── short_term.py       # 对话压缩器
│   │   └── conversation_store.py  # PG持久化
│   ├── security/            # 安全四道防线
│   ├── observability/       # OTel + Prometheus + loguru
│   ├── evaluation/          # 评测 (28用例 + LLM-Judge + RAG Triad)
│   ├── models/              # Pydantic Schema + SQLAlchemy ORM
│   ├── database/            # PG/Redis引擎管理
│   ├── services/            # 业务服务 (Chat/Text2SQL)
│   └── scripts/             # 运维脚本 (init_db/vector_store)
├── frontend/                # Vue 3 SPA
│   └── src/
│       ├── views/           # Chat / Troubleshoot / Consumables / Report / Admin
│       ├── components/      # 8个组件 (MessageBubble/Skeleton/ErrorBanner...)
│       ├── composables/     # useSSE 流式处理
│       ├── stores/          # Pinia 状态管理 (chat/app)
│       └── api/             # HTTP + SSE 客户端
├── tests/                   # 21个测试文件 (单元+集成+E2E+数据库)
├── alembic/                 # 数据库迁移
├── deploy/                  # Docker Compose + Dockerfile
├── data/                    # 知识文档 (7类16文件) + 路由关键词
└── docs/                    # 文档
```

## 常用命令

```bash
# 依赖
make install              # 安装依赖
make update               # 升级依赖

# 代码质量
make lint                 # ruff 检查
make lint-fix             # 自动修复

# 测试
make test                 # 全部测试
make test-cov             # 含覆盖率
make test-integration     # 数据库集成测试 (需要 POSTGRES_DSN)

# 评测
make eval                 # 全部 28 条用例
make eval-easy            # 仅简单难度
# 带 LLM Judge:
uv run python -m smart_qa.evaluation.runner --judge-llm

# 数据库
make db-init              # 初始化 PG 表
make db-migrate           # Alembic upgrade head
make db-migrate-check     # 检查迁移状态
make db-migrate-new msg="add_xxx"  # 生成新迁移
make vector-init          # 导入知识库到 Milvus

# Docker
make docker-up            # 全部启动
make docker-up-infra      # 仅 PG + Redis + Milvus
```

## 添加新场景

1. `scenarios/` 新建 `xxx_scenario.py`（实现 `run(state)`）
2. `agent/agents/router_agent.py` 在 `INTENT_KEYWORDS` 添加意图关键词
3. `data/router_keywords.json` 同步更新
4. `agent/graph.py` 注册节点 + 路由边
5. `evaluation/dataset.py` 添加测试用例

## 环境变量

完整配置见 [.env.example](../.env.example)，核心项:

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API Key | — |
| `LLM_BASE_URL` | LLM API 地址 | — |
| `POSTGRES_DSN` | PG 连接 | `postgresql+asyncpg://user:password@localhost:5432/agent` |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6379/0` |
| `MILVUS_HOST` | Milvus 地址 | `localhost` |
| `EMBEDDING_BACKEND` | 嵌入后端 (local/ollama/api) | `api` |
| `EMBEDDING_FALLBACK_MODEL` | 本地回退模型 (空=不启用) | — |
| `AGENT_TIMEOUT` | Agent 超时 (秒) | `60` |
| `CACHE_TTL` | 语义缓存 TTL (秒) | `1800` |
| `CHUNK_SIZE` | 文档分片大小 | `500` |
| `TROUBLESHOOT_MAX_ROUNDS` | 最大诊断轮次 | `5` |
| `REFLECTION_MAX_ROUNDS` | 反思最大迭代 | `3` |

## 调试

```bash
# 测试 LLM 连接
uv run python -c "from smart_qa.deps import get_llm_client; llm=get_llm_client(); print(llm.invoke('hi').content)"

# 测试意图分类
uv run python -c "from smart_qa.agent.agents.router_agent import RouterAgent; r=RouterAgent(); print(r.classify('怎么重置Wi-Fi'))"

# 测试关键词分类 (无LLM)
uv run python -c "from smart_qa.agent.agents.router_agent import RouterAgent; r=RouterAgent(llm_client=None); print(r._keyword_classify('它安静模式续航多久'))"

# Swagger UI
open http://localhost:8000/docs

# 评测单条
uv run python -m smart_qa.evaluation.runner --scenario qa --judge-llm
```
