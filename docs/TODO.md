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
