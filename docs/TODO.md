# TODO：系统未实现功能清单

> 本文档对照 [技术设计文档](./ARCHITECTURE.md) 和 [完整设计文档](../../jhy/jhy扫地机器人的智能问答助手.md)，
> 列出代码尚未实现的功能模块。优先级按面试冲击力 + 实际价值排列。

---

## P0 — 核心缺失（影响面试印象）

### 1. 语义缓存层

**设计文档位置：** 3.4 缓存策略 · 3.5.4 召回兜底机制  
**对应代码：** `src/smart_qa/memory/cache.py` 文件存在但未被任何代码 import  
**原因：** 每个请求都走完整 Agent 链路，相同问题重复消耗 Token

```python
# 需在 Scenario.run() 第一行接入
from smart_qa.memory.cache import SemanticCache
cache = SemanticCache()
result = await cache.get(query)
if result:
    return result  # 直接返回，不走 LLM
```

**面试加分点：** 高频问题 < 2ms 返回，省 Token 成本。

---

### 2. 记忆层持久化写入（LTM）

**设计文档位置：** 3.3 记忆系统设计  
**对应代码：** `src/smart_qa/agent/graph.py` 中 `guard_check → END` 之间没有 memory 节点  
**原因：** MemorySaver 只做 State 快照（崩溃恢复），不做用户画像/偏好持久化

```python
# 在 graph.py 中新增节点
workflow.add_node("memory_writer", memory_writer_node)
workflow.add_edge("guard_check", "memory_writer")
workflow.add_edge("memory_writer", END)
```

**memory_writer_node 职责：**
- 从对话中提取"确信不会变的事实"（设备型号、户型、偏好）
- 写入 PostgreSQL `user_profiles` 表
- 不是所有对话都写入，只写入 LTM 层级的信息

---

### 3. 多轮对话支持

**设计文档位置：** 2.3 故障排查场景（多轮对话状态管理）  
**对应代码：** `src/smart_qa/api/routes/chat.py`  
**现状：** `RedisClient.get_messages()` / `update_session()` 已实现，但 `chat.py` 没调用

```python
# chat.py — invoke 前加载历史
history = await RedisClient.get_messages(state["session_id"])
if history:
    state["messages"] = history + state["messages"]

# chat.py — invoke 后保存
await RedisClient.update_session(state["session_id"], {
    "messages": result.get("messages", state["messages"]),
})
```

---

### 4. LangGraph Store（长期记忆基础设施）

**设计文档位置：** 3.3 记忆系统设计  
**对应代码：** `src/smart_qa/agent/graph.py`  
**方案：** `PostgresStore` 替代手写 `memory/*.py`

```python
uv add langgraph-checkpoint-postgres

# graph.py
from langgraph.store.postgres import PostgresStore
store = PostgresStore(connection_string=settings.postgres_dsn)
graph = builder.compile(checkpointer=memory, store=store)
```

**当前 `memory/` 目录下 4 个文件 (`cache.py`, `short_term.py`, `long_term.py`, `task_memory.py`) 全为死代码，未被任何模块 import，可直接清理。**

---

## P1 — 功能缺失

### 5. `/chat/stream` 端点安全缺失

**对应代码：** `src/smart_qa/api/routes/chat.py:79`

```python
@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    _rl: None = Depends(check_rate_limit),   # ✅
    # _sec: None = Depends(check_security),  # ❌ 缺失
):
```

**修复：** 添加 `_sec` 依赖。

### 6. Router `"done"` 路径跳过 guard

**对应代码：** `src/smart_qa/agent/graph.py`

```python
"done": END,  # → 应改为 "done": "guard_check"
```

走 `done` 的请求直接跳到 END，跳过了 `guard_check` 和 output sanitization。

### 7. Stream 端点缺少输出过滤

**对应代码：** `src/smart_qa/api/stream_handler.py`  
**修复：** SSEStreamHandler 中每段 token 输出前调 `security.check_output()`

---

## P2 — 高阶功能

### 8. 报告生成 Agent

**设计文档位置：** 2.4 耗材管理与购买推荐场景  
**原因：** 用户需要"生成我的使用报告"功能，目前无对应 Scenario

### 9. 设备控制（MCP 工具）

**对应代码：** `src/smart_qa/agent/tools/mcp_client.py` 已存在但未接入 Scenario  
**原因：** 需要真实的 IoT 设备或模拟器

### 10. Human-in-the-Loop

**设计文档位置：** 3.5.5 Agent 防无限循环设计  
**原因：** 关键操作（定时打扫、付款）需要人类确认

---

## P3 — 长期改进

### 11. Reranker（重排序）

**对应代码：** `src/smart_qa/rag/reranker.py` 已实现，但 `MultiLayerRetriever` 未调用  
**接入方式：** 在语义检索 top_k=20 后 rerank → top_k=3

### 12. Eval 驱动的 Prompt 版本管理

**对应代码：** `src/smart_qa/evaluation/` 已实现数据集 + LLM-as-Judge，但无 CI 自动化  
**需要：** 接入 CI Pipeline，每次改 Prompt 自动跑 Eval

### 13. LangSmith 可观测

**对应代码：** `src/smart_qa/observability/` 有 Logger + Prometheus，无 LangSmith  
**原因：** 需要 LangSmith API Key 配置

---

## 已完成的（从 TODO 移除）

| 功能 | 对应代码 | 完成时间 |
|------|---------|---------|
| **引用标注 & 幻觉检测** | `src/smart_qa/rag/citation.py` | ✅ |
| **PDF 文档解析** | `DocumentParser`（PyMuPDF + Unstructured 预留） | ✅ |
| **BM25 持久化** | `BM25Index.save()` / `load()` / `add_documents()` | ✅ |
| **知识库管理 API** | upload / reload / status / files / BM25 rebuild | ✅ |
| **文档上传追踪** | `KnowledgeFile` 表（PostgreSQL） | ✅ |
| **上传后 BM25 增量更新** | upload 端点自动调用 `add_documents()` | ✅ |
| **MilvusClient 新 API** | 全线迁移，0 弃用警告 | ✅ |
| **Logger 格式修复** | loguru 模式下取消 `_fmt` 转换 | ✅ |
| **Server 配置化** | `HOST` / `PORT` 通过 `.env` 配置 | ✅ |

---

## 实现状态摘要

| 模块 | 设计文档 | 代码 | 状态 |
|------|---------|------|------|
| Router Agent | ✅ 描述 | ✅ | 完成 |
| QA Scenario | ✅ | ✅ | 完成 |
| Troubleshoot Scenario | ✅ | ✅ | 完成 |
| Consumables Scenario | ✅ | ✅ | 完成 |
| 四层召回 | ✅ 3.5.4 | ✅ | 完成 |
| 三重防循环 | ✅ 3.5.5 | ✅ | 完成 |
| 安全四道防线 | ✅ 3.5.2 | ✅ | 完成 |
| 三层限流 | ✅ 3.5.1 | ✅ | 完成 |
| 引用标注 & 幻觉检测 | ✅ 3.5.4 | ✅ | 完成 |
| DocumentParser（PDF） | ✅ | ✅ | 完成 |
| BM25 持久化 | ✅ | ✅ | 完成 |
| 知识库管理 API | ✅ | ✅ | 完成 |
| MilvusClient 迁移 | ✅ | ✅ | 完成 |
| 语义缓存 | ✅ 3.4 | ❌ | **待实现** |
| 记忆层持久化 | ✅ 3.3 | ❌ | **待实现** |
| 多轮对话 | ✅ 2.3 | ❌ | **待实现** |
| LangGraph Store | 🟡 | ❌ | **待实现** |
| Stream 安全 | ✅ 3.5.2 | ❌ | **待修复** |
| Reranker 接入 | 🟡 8章 P0 | 🟡 代码已有 | **待接入** |
| Eval 自动化 | 🟡 8章 P0 | 🟡 代码已有 | **待接入** |
