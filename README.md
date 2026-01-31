# 基于 LangGraph 的多 Agent 智能问答系统

> 面向消费级智能客服场景的多 Agent 问答系统，支持知识问答、故障排查、耗材管理三大业务场景。
>
> 后端 FastAPI + LangGraph + Milvus + PostgreSQL，前端 Vue 3 + Tailwind CSS。

## 系统架构

```
客户端 (Vue 3 SPA)
    │
接入层 (FastAPI + SSE 流式)
    │
安全层 (Depends 依赖注入: 限流 → 敏感词 → 注入防护 → 输出过滤)
    │
编排层 (LangGraph StateGraph)
    ├── Router Agent       → 意图分类与场景路由
    ├── RAG Agent          → 四层召回 + LLM 生成
    ├── Action Agent       → MCP 工具调用
    └── Report Agent       → 使用报告生成
    │
服务层 (Chat / Troubleshoot / Consumable / Report Service)
    │
数据层
    ├── models/   (SQLAlchemy ORM)
    ├── schemas/  (Pydantic 请求/响应)
    └── knowledge/ (Milvus 向量检索 + BM25)
    │
记忆层
    ├── L1: Redis 语义缓存     (相似度 > 0.95 命中)
    ├── L2: 短期对话记忆       (滑动窗口 + 摘要压缩)
    ├── L3: 长期用户画像       (设备/偏好/历史)
    └── L4: 任务记忆           (故障排查进度追踪)
    │
基础设施 (PostgreSQL + Redis + Milvus + MinIO)
```

## 三大业务场景

| 场景 | 示例问题 | 核心流程 |
|------|---------|---------|
| 📖 知识问答 | "扫地机卡在门槛怎么办？" | 语义缓存 → 四层召回(语义→改写→BM25→LLM) → 引用标注 → 反思优化 |
| 🔧 故障排查 | "机器不工作了，错误码E05" | 错误码精确匹配 / 决策树引导排查 → 多轮对话 → 3轮未果转人工 |
| 🧹 耗材管理 | "边刷该换了，买什么型号？" | 设备识别 → 兼容表查询 → 更换周期判断 → 原装/第三方推荐 → HITL 确认 |

## 技术栈

| 层 | 技术 |
|---|------|
| **后端框架** | FastAPI + Uvicorn |
| **Agent 编排** | LangGraph (StateGraph) + LangChain |
| **向量检索** | Milvus + sentence-transformers (BAAI/bge-small-zh-v1.5) |
| **关键词检索** | BM25 (自实现倒排索引) |
| **数据库** | PostgreSQL (asyncpg + SQLAlchemy 2.0) |
| **缓存** | Redis (语义缓存 + 会话存储 + 限流计数) |
| **包管理** | uv (pyproject.toml) |
| **前端** | Vue 3 + Vite + Tailwind CSS + Pinia |
| **可观测** | Prometheus + OpenTelemetry |
| **安全** | AC 自动机 (pyahocorasick) + Prompt 注入检测 |
| **工具协议** | MCP (Model Context Protocol) |
| **部署** | Docker Compose |

## 快速开始

### 前置条件

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) (Python 包管理器)
- Docker & Docker Compose
- Node.js ≥ 18 (前端开发)

### 后端启动

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env: 填入 LLM_API_KEY 等

# 3. 启动基础设施 (PostgreSQL / Redis / Milvus)
docker compose -f deploy/docker-compose.yml up -d postgres redis milvus

# 4. 初始化知识库 & 数据库
uv run python -m app.scripts.init_vector_store
uv run python -m app.scripts.init_db

# 5. 启动后端 (http://localhost:8000)
uv run python -m app.main

# 6. 验证
curl http://localhost:8000/health
curl http://localhost:8000/docs        # Swagger UI
```

### 前端启动

```bash
cd frontend
npm install
npm run dev                             # http://localhost:5173
```

### 一键部署

```bash
docker compose -f deploy/docker-compose.yml up -d
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/chat` | 普通对话 (JSON 请求/响应) |
| `POST` | `/api/v1/chat/stream` | SSE 流式对话 (逐 token 输出) |
| `GET` | `/api/v1/session/{id}/history` | 会话历史记录 |
| `POST` | `/api/v1/approve` | HITL 确认 (approve/reject/modify) |
| `GET` | `/health` | 健康检查 |
| `GET` | `/metrics` | Prometheus 指标 |
| `GET` | `/docs` | Swagger API 文档 |

### 对话请求示例

```json
POST /api/v1/chat
{
  "user_id": "U1001",
  "message": "怎么设置定时清扫？",
  "session_id": ""
}
```

### SSE 事件类型

```
event: status    → {"stage": "意图识别", "message": "正在理解您的问题..."}
event: token     → {"text": "定时"}
event: citation  → {"message": "回答基于知识库内容生成"}
event: done      → {"message": "回答完成", "intent": "qa"}
event: error     → {"message": "错误详情"}
```

## 项目结构

```
smart-qa-agent-system/
├── app/
│   ├── main.py                        # FastAPI 入口 & 生命周期
│   ├── core/                          # 核心配置 (参照 FastAPI 全栈模板)
│   │   ├── config.py                  # Settings — pydantic-settings
│   │   ├── security.py                # 限流 + 敏感词 + 注入防护 + 输出过滤
│   │   ├── database.py                # SQLAlchemy 异步引擎 & 会话工厂
│   │   └── dependencies.py            # FastAPI Depends() 集中管理
│   ├── models/                        # SQLAlchemy ORM 表定义
│   │   ├── session.py                 # 会话记录
│   │   ├── device.py                  # 用户设备绑定
│   │   ├── consumable.py              # 耗材订单
│   │   └── usage.py                   # 设备使用日志
│   ├── schemas/                       # Pydantic 请求/响应模型
│   │   ├── chat.py                    # ChatRequest / ChatResponse
│   │   ├── device.py                  # DeviceStatus / ScheduleCreate
│   │   └── report.py                  # UsageStats / ReportResponse
│   ├── api/                           # API 接入层
│   │   ├── deps.py                    # 依赖注入 (check_rate_limit / check_security)
│   │   ├── routes/                    # 按域拆分的路由
│   │   │   ├── chat.py                # POST /chat, /chat/stream
│   │   │   ├── session.py             # GET /session/{id}/history
│   │   │   └── approval.py            # POST /approve
│   │   └── stream_handler.py          # SSE 流式事件封装
│   ├── services/                      # 业务逻辑层
│   │   ├── chat_service.py            # 对话编排 (缓存→RAG→反思)
│   │   ├── troubleshoot_service.py    # 决策树 + 错误码诊断
│   │   ├── consumable_service.py      # 兼容性查询 + 推荐
│   │   └── report_service.py          # 月报/周报/异常/耗材提醒
│   ├── agent/                         # LangGraph Agent 编排
│   │   ├── graph.py                   # StateGraph 主图
│   │   ├── state.py                   # AgentState 状态定义
│   │   ├── router_agent.py            # 意图分类与场景路由
│   │   ├── rag_agent.py               # RAG 检索增强生成
│   │   ├── action_agent.py            # MCP 工具调用执行
│   │   ├── report_agent.py            # 使用报告生成
│   │   ├── reflection.py              # 自我反思 & 答案优化
│   │   ├── hitl.py                    # 人机协同确认
│   │   ├── guards/loop_detector.py    # 三重防循环检测
│   │   └── prompts/                   # CoT 思维链提示模板
│   ├── knowledge/                     # 知识检索层
│   │   ├── embedding.py               # Embedding 模型 (BGE-small-zh)
│   │   ├── bm25.py                    # BM25 倒排索引
│   │   ├── retriever.py               # 四层召回协调器
│   │   └── citation.py                # 引用追踪 & 幻觉检测
│   ├── memory/                        # 四层记忆系统
│   │   ├── semantic_cache.py          # L1: Embedding 语义缓存
│   │   └── compression.py             # L2: 窗口截断 + 摘要压缩
│   ├── security/                      # 安全模块 (兼容层)
│   ├── observability/                 # 可观测 (Prometheus + OTEL)
│   ├── tools/                         # MCP 工具集 (设备控制)
│   ├── scenarios/                     # 业务场景入口
│   ├── evaluation/                    # 评测数据集 + 运行器
│   └── scripts/                       # 运维脚本
├── frontend/                          # Vue 3 前端 SPA
│   └── src/
│       ├── views/                     # Chat / Troubleshoot / Consumables / Report / Admin
│       ├── components/                # StatusPulse / MessageBubble / Sidebar ...
│       ├── composables/               # useSSE
│       ├── stores/                    # Pinia (chat / app)
│       └── api/                       # fetch 封装
├── deploy/                            # 部署配置
│   ├── docker-compose.yml             # 6 服务编排
│   ├── Dockerfile                     # uv 构建
│   └── .env.example                   # 部署环境变量
├── data/knowledge/                    # 知识库文档 (Markdown)
│   ├── user_manual/                   # 产品手册 (X30 Pro / T10 / X20 Pro)
│   ├── fault_troubleshooting/         # 故障排查指南
│   └── consumables/                   # 耗材兼容性指南
├── tests/                             # 测试
├── pyproject.toml                     # uv 包管理 & 项目元数据
└── README.md
```

## 关键技术

### 四层召回兜底

```
L1: 语义检索    → sentence-transformers + Milvus 向量检索    (置信度 0.95)
L2: Query 改写  → LLM 改写查询 → 重新语义检索               (置信度 0.85)
L3: BM25 关键词 → 倒排索引精确匹配 (错误码/型号)             (置信度 0.70)
L4: LLM 自身知识 → 模型参数内知识 (注明不确定性)             (置信度 0.30)
```

### 三重防循环

| 防线 | 机制 |
|------|------|
| 第一道 | 最大步数限制 (默认 15 步) |
| 第二道 | 重复工具调用检测 (连续 3 次相同 → 判定循环) |
| 第三道 | 语义相似度判断 (连续 3 次输出相似 → 判定死循环) |

### 四层记忆系统

| 层级 | 存储 | TTL | 用途 |
|------|------|-----|------|
| L1 | Redis 语义缓存 | 30 min | 高频问答命中 (cosine > 0.95) |
| L2 | Redis 会话存储 | 1 hour | 滑动窗口 (最近 6 轮) + 摘要压缩 |
| L3 | PostgreSQL + Redis | 持久 | 用户画像 (设备型号 / 偏好 / 耗材记录) |
| L4 | Redis session | 30 min | 任务状态追踪 (故障排查到第几步) |

### 安全四道防线

```
请求 → [1] AC自动机敏感词 → [2] Prompt注入检测 → Agent处理 → [3] 代码注入检测 → [4] PII输出过滤 → 响应
```

### 代码架构 (参照 FastAPI 全栈模板)

```
core/ (配置/安全/数据库) → models/ (ORM) + schemas/ (Pydantic)
  → services/ (业务逻辑) → api/routes/ (纯路由) ← api/deps.py (Depends 注入)
```

## 开发指南

### 运行测试

```bash
uv run pytest                           # 全部测试
uv run pytest tests/test_imports.py -v  # 导入验证
```

### 添加依赖

```bash
uv add <package>                # 生产依赖
uv add --dev <package>          # 开发依赖
```

### 代码质量

```bash
uv run ruff check app/          # Lint
```

### 评测

```bash
uv run python -m app.evaluation.runner
```

## 许可

MIT License
