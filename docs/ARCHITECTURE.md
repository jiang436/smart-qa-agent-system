# 智能问答 Agent 系统 — 技术架构

## 一、系统架构

```mermaid
flowchart TB
    subgraph 接入["接入层"]
        UI[Vue 3 SPA]
        API[FastAPI + SSE 流式]
    end

    subgraph 安全["安全层"]
        RL[Rate Limiter<br>令牌桶三层限流]
        SF[Sensitive Filter<br>AC自动机 + 注入检测 + 代码检测 + 输出脱敏]
    end

    subgraph 编排["编排层 — LangGraph StateGraph"]
        MR[Memory Reader<br>加载用户画像]
        Router[Router Agent<br>意图分类]
        QA[RAG Agent<br>知识问答]
        TS[故障排查<br>决策树引导]
        CS[耗材管理<br>兼容表 + HITL]
        DC[设备控制<br>模拟器/IoT]
        RP[报告生成<br>使用统计]
        MW[Memory Writer<br>持久化 LTM]
    end

    subgraph 检索["知识检索层"]
        SR[语义检索<br>Milvus 向量<br>top-20 召回]
        RN[Reranker<br>Cross-Encoder<br>top-3 精选]
        BM[BM25 关键词<br>倒排索引]
        LLM[LLM 兜底<br>模型自身知识]
    end

    subgraph 记忆["记忆层"]
        SC[语义缓存<br>Redis Hash + TTL]
        CK[Checkpoint<br>MemorySaver]
        ST[PostgresStore<br>LangGraph 长期记忆]
    end

    subgraph 可观测["可观测层"]
        OT[OpenTelemetry<br>FastAPI / httpx / SQLAlchemy]
        PR[Prometheus<br>指标 /metrics]
        SN[SigNoz<br>自托管追踪 UI]
    end

    接入 --> 安全 --> 编排
    编排 --> 检索 --> 编排
    编排 --> 记忆
    编排 -.-> 可观测
```

## 二、核心流程

```
POST /api/v1/chat
  │
  ├── check_rate_limit(user_id)          # 1. 令牌桶限流
  ├── check_security(message)            # 2. 敏感词 + Prompt注入 + 代码注入
  │
  ├── graph.ainvoke(state)
  │     │
  │     ├── memory_reader                # 加载用户画像 (PostgresStore)
  │     ├── RouterAgent.route()          # 意图分类
  │     ├── Scenario.run()               # 场景执行
  │     │     ├── SemanticCache.get()    # L1 缓存命中
  │     │     ├── MultiLayerRetriever    # 四层召回 + Reranker
  │     │     ├── LLM 生成回答
  │     │     └── SemanticCache.set()    # 写入缓存
  │     ├── LoopDetector.check()         # 3. 三重防循环
  │     └── memory_writer                # 持久化 LTM (PostgresStore)
  │
  └── security.check_output(answer)      # 4. PII 输出脱敏
```

## 三、模块清单

| 模块 | 路径 | 状态 |
|------|------|------|
| Router Agent | `agent/agents/router_agent.py` | ✅ 6意图分类 (LLM+关键词) |
| QA 场景 | `scenarios/qa_scenario.py` | ✅ 语义缓存 + RAG |
| 故障排查 | `scenarios/troubleshoot_scenario.py` | ✅ 决策树 + 多轮 |
| 耗材管理 | `scenarios/consumables_scenario.py` | ✅ 推荐 + HITL + 下单 |
| 设备控制 | `scenarios/device_control_scenario.py` | ✅ 6种命令 (设备模拟器) |
| 报告生成 | `scenarios/report_scenario.py` | ✅ 月度/周/异常/耗材 |
| 四层召回 | `rag/retrieval.py` | ✅ 语义→改写→BM25→LLM |
| Reranker | `rag/reranker.py` | ✅ Cross-Encoder / 启发式降级 |
| BM25 索引 | `knowledge/bm25.py` | ✅ 增量更新 + 持久化 |
| 语义缓存 | `memory/cache.py` | ✅ Redis Hash + TTL |
| 长期记忆 | `agent/graph.py` (PostgresStore) | ✅ 用户画像持久化 |
| 多轮对话 | `api/routes/chat.py` | ✅ MemorySaver + PG |
| 三重防循环 | `agent/guards/loop_detector.py` | ✅ 硬上限 + 运行时 + 强制 |
| 安全四道防线 | `security/` | ✅ 敏感词/注入/代码/PII |
| 三层限流 | `security/` | ✅ 全局 + 用户 + token |
| E2E 评测 | `evaluation/runner.py` | ✅ 18用例 + LLM-Judge |
| 可观测 | `observability/` | ✅ OTel + SigNoz / Prometheus |

## 四、技术选型

| 模块 | 选型 | 备选 |
|------|------|------|
| Agent 框架 | LangGraph StateGraph | CrewAI |
| 向量库 | Milvus | Qdrant / Chroma |
| 关系库 | PostgreSQL | — |
| 缓存 | Redis | local dict |
| 重排序 | BGE-Reranker-v2-m3 | 启发式降级 |
| 可观测 | OTel + SigNoz / Prometheus | Logfire / Grafana |
| 前端 | Vue 3 + Vite | Streamlit |
