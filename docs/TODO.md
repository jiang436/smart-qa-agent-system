# TODO：系统未实现功能清单

> 本文档对照 [技术设计文档](./ARCHITECTURE.md) 和 [完整设计文档](../../jhy/jhy扫地机器人的智能问答助手.md)，
> 列出代码尚未实现的功能模块。优先级按面试冲击力 + 实际价值排列。

---

## P0 — 核心缺失（影响面试印象）

### 1. 语义缓存（Redis 后端）

**设计文档位置：** 3.4 缓存策略 · 3.5.4 召回兜底机制  
**代码状态：** `SemanticCache` 类 ✅ 已实现，已接入 `QAScenario` / `RAGAgent` / `ChatService`  
**当前限制：** ✅ 本地 dict 可用 | ✅ Redis Hash 后端已实现（SCAN + 余弦相似度） | ✅ 自动检测 `RedisClient._client` | ✅ TTL 支持  
**下一步：** 大规模场景 > 10 万条可升级 Redis Stack `FT.SEARCH`（当前 SCAN 遍历对缓存规模够用）

---

### 2. 记忆层持久化写入（LTM）

**设计文档位置：** 3.3 记忆系统设计  
**代码状态：** ✅ `memory_writer_node` 已实现，`graph.py` 已接入 | ✅ `UserProfile` 表已创建 | ✅ 模式匹配提取（设备/偏好/户型） | ✅ UPSERT 到 PostgreSQL | ✅ 静默失败不阻塞主流程  
**当前限制：** 仅支持中文关键词匹配，英文用户需扩展 `_MODE_KEYWORDS` | 无 LLM 提取（成本原因，纯模式匹配）

---

### 3. 无（已在多轮对话支持中实现 — PG 持久化）

### 4. 无（已在 LangGraph Store 中实现）

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

### 6. 无（已在记忆层持久化中修复）

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
| 语义缓存（Redis） | ✅ 3.4 | ✅ | **完成（Hash + TTL + 写穿）** |
| 记忆层持久化 | ✅ 3.3 | ✅ | **完成（模式匹配 + UPSERT）** |
| 多轮对话 | ✅ 2.3 | ✅ | **完成（MemorySaver + Redis 双重备份）** |
| LangGraph Store | ✅ 3.3 | ✅ | **完成（PostgresStore + 自动注入）** |
| Stream 安全 | ✅ 3.5.2 | ❌ | **待修复** |
| Reranker 接入 | 🟡 8章 P0 | 🟡 代码已有 | **待接入** |
| Eval 自动化 | 🟡 8章 P0 | 🟡 代码已有 | **待接入** |
