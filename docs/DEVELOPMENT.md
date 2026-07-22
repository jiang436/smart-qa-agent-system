# 开发指南

## 环境要求

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose（基础设施用）
- Node.js >= 18（前端开发）

## 快速启动

```bash
# 1. 安装依赖
make install

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env: 必填 LLM_API_KEY + LLM_BASE_URL

# 3. 启动基础设施
make docker-up-infra   # PostgreSQL + Redis + Milvus

# 4. 初始化
make db-init           # 创建数据库表
make db-migrate        # Alembic 迁移
make vector-init       # 导入知识库到 Milvus

# 5. 启动后端
make dev               # http://localhost:8000

# 6. 启动前端 (另开终端)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## 项目结构

```
smart-qa-agent-system/
├── src/smart_qa/              # 后端 (~40 文件)
│   ├── web.py                 # FastAPI 入口 + lifespan
│   ├── config.py              # pydantic-settings (30+ 配置项)
│   ├── di.py                  # DI 容器
│   ├── deps.py                # FastAPI Depends 依赖访问器
│   ├── exceptions.py          # 异常层次 (11 类型)
│   ├── agent/                 # LangGraph 编排
│   │   ├── graph.py           # 7 节点 StateGraph
│   │   ├── state.py           # AgentState TypedDict
│   │   ├── persona.py         # 统一人设 + 三层响应
│   │   ├── agents/            # Router / RAG / Reflection
│   │   ├── guards/            # LoopDetector 四重防循环
│   │   └── prompts/           # CoT 模板 (rag/router/troubleshoot)
│   ├── api/                   # REST + SSE
│   │   ├── routes/            # chat / knowledge / session
│   │   └── stream_handler.py  # SSE 流式处理
│   ├── rag/                   # 检索增强
│   │   ├── retrieval.py       # MultiLayerRetriever 四层召回
│   │   ├── reranker.py        # Cross-Encoder 重排 (RAGFlow 设计)
│   │   ├── citation.py        # CitationTracker + 幻觉检测
│   │   └── chunking.py        # SmartDocumentSplitter (4 策略)
│   ├── knowledge/             # 知识层
│   │   ├── bm25.py            # BM25Index (持久化 + 预计算)
│   │   ├── vector_store.py    # Embedding 模型 (可插拔)
│   │   ├── embedding_backends.py  # Local/Ollama/API/Fallback
│   │   ├── knowledge_graph.py # 知识图谱 (兼容/错误码/多跳)
│   │   └── document_parser.py # PDF/Markdown/TXT 解析
│   ├── memory/                # 记忆系统
│   │   ├── cache.py           # SemanticCache (Redis + 本地)
│   │   ├── short_term.py      # MemoryCompressor
│   │   └── conversation_store.py  # PG 会话持久化
│   ├── scenarios/             # QA / 故障排查
│   ├── models/                # SQLAlchemy ORM + Pydantic
│   ├── database/              # PG 引擎 + Redis 客户端
│   ├── security/              # 限流 / 注入检测 / 脱敏
│   ├── observability/         # Loguru 日志
│   └── scripts/               # init_db / init_vector_store
├── frontend/                  # Vue 3 SPA
│   ├── src/views/             # ChatView / AdminView
│   ├── src/components/        # MessageBubble / Sidebar / CitationCard 等
│   ├── src/stores/            # Pinia (chat / app)
│   ├── src/api/               # HTTP + SSE 客户端
│   └── tests/                 # vitest (33 用例)
├── tests/                     # pytest (429 用例, 25 文件)
├── test_results/              # 评测报告 (JSON + Markdown)
├── alembic/                   # 数据库迁移
├── deploy/                    # Docker Compose + Dockerfile
├── data/knowledge/            # 知识文档 (7 类 16 文件)
└── docs/                      # 技术文档 + 截图
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
make test-integration     # 数据库集成测试

# 数据库
make db-init              # 初始化 PG 表
make db-migrate           # Alembic 迁移
make db-migrate-new       # 生成新迁移
make vector-init          # 导入知识库到 Milvus

# Docker
make docker-up            # 全部启动
make docker-up-infra      # 仅 PG + Redis + Milvus
```

## 调试

```bash
# 测试 LLM 连接
uv run python -c "from smart_qa.deps import get_llm_client; llm=get_llm_client(); print(llm.invoke('hi').content)"

# 测试意图分类 (关键词模式)
uv run python -c "from smart_qa.agent.agents.router_agent import RouterAgent; r=RouterAgent(); print(r.classify('怎么重置Wi-Fi'))"

# Swagger UI
open http://localhost:8000/docs
```
