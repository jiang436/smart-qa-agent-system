# 系统架构

## 整体架构

```
客户端 (Vue 3 SPA)
    │
接入层 (FastAPI + SSE 流式)
    │  api/deps.py: check_rate_limit → check_security
    │
编排层 (LangGraph StateGraph)
    │  agent/graph.py: router → scenario → guard_check → END
    ├── Router Agent       意图分类 (qa / troubleshoot / consumables / general)
    ├── RAG Agent          四层召回 + LLM 生成 + 引用标注 + 幻觉检测
    ├── Action Agent        MCP 工具调用 (设备控制)
    └── Report Agent       月度/周度/异常/耗材报告
    │
服务层 (app/services/)
    ├── ChatService        对话编排 (缓存 → RAG → 反思 → 记忆写入)
    ├── TroubleshootService 决策树诊断 + 错误码匹配
    ├── ConsumableService  兼容性查询 + 原装/第三方推荐
    └── ReportService      报告生成
    │
数据层
    ├── models/    SQLAlchemy ORM (Session / UserDevice / ConsumableOrder / DeviceUsageLog)
    ├── schemas/   Pydantic 请求/响应 (ChatRequest / DeviceStatus / UsageStats)
    └── knowledge/ 四层召回 (语义 → 改写 → BM25 → LLM)
    │
记忆层 (app/memory/)
    ├── L1: SemanticCache       Embedding 相似度缓存 (>0.95 命中)
    ├── L2: MemoryCompressor    滑动窗口 (6轮) + LLM 摘要压缩
    ├── L3: 用户画像             PostgreSQL 持久化
    └── L4: 任务记忆             Redis session 临时状态
    │
基础设施
    ├── PostgreSQL  结构化数据 (用户/设备/订单/日志)
    ├── Redis       缓存 + 会话 + 限流计数
    ├── Milvus      向量检索
    └── MinIO       对象存储 (Milvus 后端)
```

## 代码架构 (参照 full-stack-fastapi-template)

```
app/
├── core/          # 核心配置
│   ├── config.py       Settings (pydantic-settings, 读 .env)
│   ├── security.py     限流 + 敏感词 + 注入防护 + 输出过滤
│   ├── database.py     SQLAlchemy 引擎 & 会话工厂
│   └── dependencies.py FastAPI Depends() 集中管理
│
├── models/        # SQLAlchemy ORM 表定义
│   ├── session.py      会话记录
│   ├── device.py       用户设备绑定
│   ├── consumable.py   耗材订单
│   └── usage.py        设备使用日志
│
├── schemas/       # Pydantic 请求/响应
│   ├── chat.py         ChatRequest / ChatResponse
│   ├── device.py       DeviceStatus / ScheduleCreate / ScheduleResponse
│   └── report.py       UsageStats / ConsumableStatus / ReportResponse
│
├── api/           # API 路由 (按域拆分)
│   ├── deps.py         check_rate_limit / check_security (Depends)
│   └── routes/
│       ├── chat.py         POST /chat, /chat/stream
│       ├── session.py      GET /session/{id}/history
│       └── approval.py     POST /approve
│
├── services/      # 业务逻辑层
│   ├── chat_service.py
│   ├── troubleshoot_service.py
│   ├── consumable_service.py
│   └── report_service.py
│
├── agent/         # LangGraph Agent 编排
│   ├── graph.py          StateGraph 主图
│   ├── state.py          AgentState 状态定义
│   ├── router_agent.py   意图分类
│   ├── rag_agent.py      RAG 检索增强生成
│   ├── action_agent.py   MCP 工具调用
│   ├── report_agent.py   报告生成
│   ├── reflection.py     自我反思
│   ├── hitl.py           Human-in-the-Loop
│   ├── guards/loop_detector.py  三重防循环
│   └── prompts/          CoT 思维链模板
│
├── knowledge/     # 知识检索层
│   ├── embedding.py     BGE-small-zh 向量化
│   ├── bm25.py          BM25 倒排索引
│   ├── retriever.py     四层召回协调器
│   └── citation.py      引用追踪 + 幻觉检测
│
├── memory/        # 四层记忆
│   ├── semantic_cache.py 语义缓存
│   └── compression.py    记忆压缩
│
├── tools/         # MCP 工具集
│   └── mcp_client.py        MCP stdio 客户端
│
├── observability/ # 可观测
│   ├── metrics.py       Prometheus 指标
│   ├── tracer.py        OpenTelemetry 追踪
│   └── token_counter.py Token 统计
│
├── evaluation/    # 评测
│   ├── dataset.py       55 个测试用例
│   ├── metrics.py       评测指标
│   └── runner.py        评测运行器
│
└── scripts/       # 运维脚本
    ├── init_db.py           建表 + 种子数据
    ├── init_vector_store.py 知识库导入 Milvus
    └── onenet_simulator.py  设备模拟器
```

## 数据流

```
POST /api/v1/chat
  │
  ▼
api/deps.py: check_rate_limit(user_id)        # 令牌桶限流
api/deps.py: check_security(message)           # 敏感词 + 注入检测
  │
  ▼
agent/graph.py: build_graph().ainvoke(state)
  │
  ├── RouterAgent.route(state)                 # LLM 意图分类
  │     └── state.intent = qa/troubleshoot/consumables/general
  │
  ├── QAScenario/TroubleshootScenario/ConsumablesScenario.run(state)
  │     ├── SemanticCache.get(query)            # L1 缓存命中?
  │     ├── RAGAgent.answer(query)
  │     │     ├── MultiLayerRetriever.retrieve()
  │     │     ├── LLM 生成
  │     │     ├── CitationTracker 引用标注
  │     │     ├── HallucinationGuard 幻觉检测
  │     │     └── ReflectionAgent 自我反思
  │     └── SemanticCache.set(query, answer)
  │
  └── LoopDetector.check(state)                # 防循环检测
        └── decide: continue / stop / done
```

## 关键技术

### 四层召回
```
L1: 语义检索    sentence-transformers + Milvus    置信度 0.95
L2: Query 改写  LLM 改写 → 重新语义检索            置信度 0.85
L3: BM25       倒排索引关键词匹配 (错误码/型号)     置信度 0.70
L4: LLM 兜底   模型自身知识 (注明不确定性)          置信度 0.30
```

### 三重防循环
1. 最大步数限制 (max_steps=15)
2. 重复工具调用检测 (连续 3 次相同)
3. 语义相似度判断 (连续 3 次输出相似)

### 安全四道防线
```
请求 → [1] AC自动机敏感词 → [2] Prompt注入检测
     → Agent处理
     → [3] 代码注入检测 → [4] PII输出脱敏 → 响应
```
