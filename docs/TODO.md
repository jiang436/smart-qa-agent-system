# TODO：系统未实现功能清单

> 本文档对照 [技术设计文档](./ARCHITECTURE.md) 和 [完整设计文档](../../jhy/jhy扫地机器人的智能问答助手.md)，
> 列出代码尚未实现的功能模块。优先级按面试冲击力 + 实际价值排列。

---

## P0 — 核心缺失（影响面试印象）

### 1. 语义缓存层

**设计文档位置：** 3.4 缓存策略 · 3.5.4 召回兜底机制  
**对应代码：** `src/memory/` 目录为空  
**原因：** 每个请求都走完整 Agent 链路，相同问题重复消耗 Token

**需要实现：**

```python
# 新增文件: src/memory/semantic_cache.py
class SemanticCache:
    """L1 语义缓存 — 相似 query 直接命中缓存回答"""

    async def get(self, query: str) -> str | None:
        """计算 query embedding → Milvus 搜索 → 相似度 > 0.95 → 返回"""

    async def set(self, query: str, answer: str):
        """写入缓存（带 TTL）"""
```

**影响链路：** 每个 Scenario.run() 的第一行先查缓存。

---

### 2. 引用标注 & 幻觉检测

**设计文档位置：** 3.5.4 召回兜底机制  
**对应代码：** `src/knowledge/` 下无 `citation.py`  
**原因：** Agent 回答不标注知识来源，用户无法验证答案可信度

**需要实现：**

```python
# 新增文件: src/knowledge/citation.py
class CitationTracker:
    """引用追踪 — 确保 LLM 回答的每句话都有知识来源"""

    def extract_citations(self, answer: str, docs: list[Document]) -> str:
        """标注引用编号 [1][2] 并附来源"""
```

**面试加分点：** Perplexity 式引用溯源，面试官一看就懂。

---

### 3. 记忆层持久化写入

**设计文档位置：** 3.3 记忆系统设计  
**对应代码：** `src/agent/graph.py` 中 guard → 之后没有 memory 节点  
**原因：** MemorySaver 只做 State 快照（崩溃恢复），不做用户画像/偏好持久化

**需要实现：**

```python
# 在 graph.py 中新增节点
workflow.add_node("memory_writer", memory_writer_node)

# 在 guard 之后、END 之前执行
workflow.add_edge("guard_check", "memory_writer")
workflow.add_edge("memory_writer", END)
```

**memory_writer_node 职责：**

- 从对话中提取"确信不会变的事实"（设备型号、户型、偏好）
- 写入 PostgreSQL `user_profiles` 表
- 不是所有对话都写入，只写入 LTM 层级的信息

---

### 4. 多轮对话支持

**设计文档位置：** 2.3 故障排查场景（多轮对话状态管理）  
**对应代码：** `src/smart_qa/api/routes/chat.py`  
**现有基础设施（但未接入）：**

| 组件 | 状态 | 说明 |
|------|------|------|
| `RedisClient.get_messages()` | ✅ 已实现 | 从 Redis 读取历史消息 |
| `RedisClient.update_session()` | ✅ 已实现 | 写入会话到 Redis |
| `GET /session/{id}/history` | ✅ 已实现 | 历史查询 API |
| `chat.py` 加载历史 | ❌ 未做 | 每次 `_create_initial_state` 重置 messages |
| 场景内传历史上下文 | 🟡 仅 `handle_general` | Router/QAScenario 等没传历史 |

**原因：** `chat.py` 的 `_create_initial_state()` 每次创建全states状态，不给 LangGraph MemorySaver 传递历史消息的机会。

**修复方案：**

```python
# chat.py — 加载历史后拼入 state
state = _create_initial_state(...)

# 从 Redis 加载历史
try:
    history = await RedisClient.get_messages(state["session_id"])
    if history:
        # 把历史消息拼到当前消息前面
        state["messages"] = history + state["messages"]
except Exception:
    pass  # 没有历史也不影响

# 走 Agent
result = await graph.ainvoke(state, config=config)

# 保存本轮对话到 Redis
await RedisClient.update_session(state["session_id"], {
    "messages": result.get("messages", state["messages"]),
    "intent": result.get("intent"),
})
```

**面试加分点：** 多轮对话是面试官最容易验证的功能（"我连续问两个相关的问题，看它能不能理解指代关系"）。不做的话第一个演示场景就露馅。

---

### 5. 记忆层：用 LangGraph Store 替代手写 memory/

**设计文档位置：** 3.3 记忆系统设计  
**当前状态：**
- `memory/cache.py`、`short_term.py`、`long_term.py`、`task_memory.py` 四个文件
- 但 **没有任何代码 import 它们**——纯死代码
- 实际靠 `LangGraph MemorySaver` + Redis（chat.py 里也没调）

**方案：LangGraph Store（开源免费）**

| 组件 | 包 | 费用 |
|------|-----|------|
| `BaseStore` | `langgraph`（已安装） | ✅ 免费 |
| `InMemoryStore` | `langgraph`（已安装） | ✅ 免费，开发测试 |
| `PostgresStore` | `langgraph-checkpoint-postgres` | ✅ 免费，需额外 pip 安装 |

```python
# 加入长期记忆存储
from langgraph.store.postgres import PostgresStore

store = PostgresStore(
    connection_string="postgresql://user:pass@localhost:5432/agent"
)

graph = builder.compile(
    checkpointer=memory,  # 短期记忆（已有 MemorySaver）
    store=store,          # 长期记忆（新增）
)

# 在 Node 中使用
async def router_node(state, config, *, store):
    # store.put(): 写入长期记忆
    await store.put(("users", user_id), "device", {"model": "X30 Pro", "sn": "SN123"})
    
    # store.search(): 查询长期记忆
    results = await store.search(("users", user_id))
```

**好处：**
- 零额外依赖（LangGraph 自带，PostgreSQL 已有）
- 自动支持命名空间隔离（`("users", user_id)` 按用户分）
- 和 MemorySaver 协同工作（短期 + 长期）
- 可以删掉当前 4 个没用的 memory/*.py 文件

**需要改动：**
- `uv add langgraph-checkpoint-postgres`
- `graph.py`: compile 时传入 `store=PostgresStore(...)`
- 在各 Scenario 的 Node 中加 `store` 参数读写记忆

---

## P1 — 功能缺失

### 4. `/chat/stream` 端点安全缺失

**当前代码：** `src/app/api/routes/chat.py` 中 stream 端点

```python
@router.post("/chat/stream")
async def chat_stream(
        request: ChatRequest,
        _rl: None = Depends(check_rate_limit),  # ✅
        _sec: None = Depends(check_security),  # ❌ 没有
):
```

**修复：** 添加 `_sec` 依赖。

### 5. Router `"done"` 路径跳过 guard

**当前代码：** `src/agent/graph.py` line 127

```python
"done": END,  # FAQ 高置信命中 → 直接返回，跳过 RAG
```

走 `done` 的请求直接跳到 END，跳过了 `guard_check` 和 output sanitization。

**修复：** 把 `"done"` 指向 `guard_check` 而不是 `END`。

### 6. Stream 端点缺少输出过滤

**当前代码：** `src/app/api/routes/chat.py` 中 stream 端点没有调用 `security.check_output()`

**修复：** 在 SSEStreamHandler 中追加输出脱敏步骤。

---

## P2 — 高阶功能

### 7. 报告生成 Agent

**设计文档位置：** 2.4 耗材管理与购买推荐场景  
**原因：** 用户需要"生成我的使用报告"功能，目前无对应 Scenario

### 8. 设备控制（MCP 工具）

**设计文档位置：** 2.5 跨房间全屋清洁场景  
**对应代码：** `src/agent/tools/mcp_client.py` 已存在但未接入 Scenario  
**原因：** 需要真实的 IoT 设备或模拟器

### 9. Human-in-the-Loop

**设计文档位置：** 3.5.5 Agent 防无限循环设计  
**原因：** 关键操作（定时打扫、付款）需要人类确认

---

## P3 — 长期改进

### 10. Reranker（重排序）

**设计文档位置：** 可扩展技术点 P0  
**对应代码：** `src/rag/reranker.py` 已实现，但未接入实际链路  
**原因：** `MultiLayerRetriever` 尚未调用 Reranker

### 11. Eval 驱动的 Prompt 版本管理

**设计文档位置：** 8.5 Prompt 版本管理  
**对应代码：** `src/evaluation/` 已实现数据集和 Judge，但无 CI 自动化  
**原因：** 需要接入 CI Pipeline

### 12. LangSmith 可观测

**设计文档位置：** 5.8 可观测  
**对应代码：** `src/observability/` 有 Logger + Prometheus，无 LangSmith  
**原因：** 需要 LangSmith API Key 配置

### 13. OCR 后端扩展（可插拔，备选）

**触发条件：** 知识库中出现大量扫描件/复杂版面文档  
**当前方案：** PyMuPDF（文字 PDF 毫秒级）+ Tesseract（扫描件降级）  
**待接入：** 百度 Unlimited-OCR（VLM 强 OCR，需 GPU 16GB+）

```python
# 架构设计：可插拔 OCRBackend 接口
class OCRBackend(ABC):
    @abstractmethod
    def extract(self, pdf_path: str) -> str: ...

class PyMuPDFBackend(OCRBackend): ...     # 文字PDF，默认
class TesseractBackend(OCRBackend): ...    # 轻量OCR
class UnlimitedOCRBackend(OCRBackend): ... # 重度扫描件，需GPU

class OCRProcessor:
    """自动选择最优 OCR 后端"""
    def process(self, path: str) -> str:
        backend = self._detect_best(path)
        return backend().extract(path)
```

**不默认开启原因：**
- 模型约 7B 参数（14GB），需要 CUDA GPU
- 推理每页 3-10 秒（vs PyMuPDF 毫秒级）
- 文字 PDF 场景下效果无差异

| 场景 | 当前方案 | Unlimited-OCR | 切换条件 |
|------|---------|---------------|---------|
| 文字 PDF | ✅ PyMuPDF 毫秒级 | ❌ 杀鸡用牛刀 | 永远不需要 |
| 扫描件 | 🟡 Tesseract 中等 | ✅ 版面理解强 | 扫描件占比 > 30% |
| 表格/合同 | 🟡 unstructured 有限 | ✅ 结构理解强 | 需要提取表格关系 |
| 用户上传图片 | ❌ 不支持 | ✅ VLM 原生支持 | P0 需求时才做 |

---

## 修复优先级建议

```text
两周冲刺推荐:

第 1 周：P0
  ├── 语义缓存（最值钱——省 Token、降延迟、面试能讲）
  ├── 引��标注（最直观——面试官一看就懂"引用溯源"）
  └── /chat/stream 安全修复（最简单的改动）

第 2 周：P1
  ├── 记忆层持久化写入
  ├── Router done 路径修复
  ├── Reranker 接入
  └── E2E Eval 报告展示
```

```markdown
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
| 语义缓存 | ✅ 3.4 | ❌ | **待实现** |
| 引用标注 | 🟡 8章 P3 | ❌ | **待实现** |
| 记忆层持久化 | ✅ 3.3 | ❌ | **待实现** |
| Stream 安全 | ✅ 3.5.2 | ❌ | **待修复** |
| Reranker | 🟡 8章 P0 | 🟡 代码已有，未接入 | **待接入** |
| Eval 自动化 | 🟡 8章 P0 | 🟡 代码已有 | **待接入** |
```
