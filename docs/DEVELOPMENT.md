# 开发指南

## 环境要求

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose（可选，基础设施用）
- Node.js ≥ 18（前端开发）

## 快速启动

```bash
# 一键启动
bash start.sh

# 或分步手动
make install            # 安装依赖
make docker-up-infra    # 启动 PostgreSQL + Redis + Milvus
make db-init            # 初始化数据库
make vector-init        # 初始化向量知识库
make dev                # 启动服务 http://localhost:8000

# 前端 (另一个终端)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## 项目结构

```
src/smart_qa/
├── web.py                 # FastAPI 入口 + 生命周期
├── config.py              # pydantic-settings 配置
├── deps.py                # 全局依赖注入
├── agent/                 # LangGraph 编排
│   ├── graph.py           # 状态图定义 (memory_reader → router → ... → memory_writer)
│   ├── state.py           # AgentState TypedDict
│   ├── agents/            # Agent 节点实现
│   └── guards/            # 防循环检测
├── api/routes/            # FastAPI 路由
│   ├── chat.py            # POST /chat, /chat/stream
│   ├── session.py         # GET /session/{id}/history
│   ├── approval.py        # POST /approve
│   └── knowledge.py       # 知识库管理
├── scenarios/             # 业务场景
│   ├── qa_scenario.py
│   ├── troubleshoot_scenario.py
│   ├── consumables_scenario.py
│   ├── device_control_scenario.py
│   └── report_scenario.py
├── rag/                   # 检索增强生成
│   ├── retrieval.py       # 四层召回引擎
│   ├── reranker.py        # 重排序
│   ├── chunking.py        # 文档分片
│   └── citation.py        # 引用标注 + 幻觉检测
├── knowledge/             # 知识库
│   ├── bm25.py            # BM25 倒排索引
│   ├── vector_store.py    # Embedding 模型
│   ├── embedding_backends.py  # 可插拔后端
│   └── document_parser.py # PDF/MD/TXT 解析
├── memory/                # 记忆系统
│   ├── cache.py           # 语义缓存 (Redis)
│   └── conversation_store.py  # 对话历史 (PG)
├── security/              # 安全
├── observability/         # 可观测
│   ├── tracer.py          # OTel 自动追踪
│   ├── metrics.py         # Prometheus 指标
│   └── logger.py          # 结构化日志
├── evaluation/            # 评测
│   ├── dataset.py         # 18 条测试用例
│   ├── runner.py          # Eval 运行器 (CLI)
│   ├── judge.py           # LLM-as-Judge
│   └── metrics.py         # 指标聚合
├── models/                # Pydantic Schema + ORM
│   ├── chat_schema.py
│   ├── device_schema.py
│   ├── approval_schema.py
│   └── report_schema.py
└── scripts/               # 运维脚本
    ├── init_db.py
    └── init_vector_store.py
```

## 常用命令

```bash
# 依赖
make install              # 安装生产依赖
make update               # 升级所有依赖

# 代码质量
make lint                 # ruff 检查
make lint-fix             # 自动修复

# 测试
make test                 # 75 条单元测试
make test-cov             # 含覆盖率

# 评测
make eval                 # 全部 18 条
make eval-easy            # 只跑简单

# 数据库
make db-init              # 初始化 PG 表
make vector-init          # 导入知识库到 Milvus

# Docker
make docker-up            # 全部启动 (含 SigNoz)
make docker-up-infra      # 仅 postgres+redis+milvus
```

## 添加新场景

1. `scenarios/` 新建 `xxx_scenario.py`（实现 `run(state)`）
2. `agent/agents/router_agent.py` 添加意图关键词
3. `agent/graph.py` 注册节点 + 路由边
4. `evaluation/dataset.py` 添加测试用例

## 环境变量

完整配置项见 [.env.example](../.env.example)，核心项:

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API Key | — |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `POSTGRES_DSN` | PG 连接 | `postgresql+asyncpg://user:password@localhost:5432/agent` |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6379/0` |
| `MILVUS_HOST` | Milvus 地址 | `localhost` |
| `EMBEDDING_BACKEND` | 嵌入模型后端 | `local` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel 上报地址 | 空=跳过 |

## 调试

```bash
# 测试 LLM 连接
uv run python -c "from smart_qa.deps import get_llm_client; llm=get_llm_client(); print(llm.invoke('hi').content)"

# 测试意图分类
uv run python -c "from smart_qa.agent.agents.router_agent import RouterAgent; r=RouterAgent(); print(r.classify('怎么重置Wi-Fi'))"

# Swagger UI
open http://localhost:8000/docs
```
