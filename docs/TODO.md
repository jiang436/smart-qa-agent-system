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

### 5. 无（已在 `/chat/stream` 安全修复中补齐 — input + output 双过滤）

### 6. 无（已在记忆层持久化中修复）

### 7. 无（已在 `/chat/stream` 安全修复中补齐 — output_filter={check_output}）

## P2 — 高阶功能

### 8. 报告生成 Agent

**设计文档位置：** 2.4 耗材管理与购买推荐场景  
**对应代码：** `scenarios/report_scenario.py` + `agent/agents/report_agent.py` 已实现  
**当前状态：** ✅ `ReportScenario.run()` 已实现，`RouterAgent` 已识别 report 意图，graph.py 已接入  
**报告类型：** monthly / weekly / consumable / abnormal（根据用户问题自动检测）

### 9. 无（已在设备控制场景中实现 — IoT 模拟器 MCP）

**对应代码：** `scenarios/device_control_scenario.py` + `agent/tools/device.py` 已增强  
**当前状态：** ✅ `DeviceControlScenario.run()` 已实现 | ✅ `DeviceManager` 新增 start_cleaning / stop_cleaning / return_to_charge / set_mode | ✅ Mock 数据含 3 个虚拟设备 | ✅ RouterAgent 识别 device_control 意图  
**支持命令：** 查状态 / 开始清扫 / 停止 / 回充 / 切换模式(安静/标准/强力) / 定时任务

### 10. Human-in-the-Loop

**设计文档位置：** 3.5.5 Agent 防无限循环设计  
**对应代码：** `scenarios/consumables_scenario.py` 两阶段 HITL 确认  
**当前状态：** ✅ 推荐 → `pending_purchase` → 用户确认/拒绝 → 订单创建/取消  
**触发场景：** 耗材购买推荐（用户说"好/确认"→创建订单；"不用了"→取消）

---

## P3 — 长期改进

### 11. Reranker（重排序）

**对应代码：** `src/smart_qa/rag/reranker.py` ✅ 已实现 | `src/smart_qa/rag/retrieval.py` ✅ 已接入  
**当前状态：** ✅ `retrieve()` 内部先取 top_k×3（≥20 条），再用 Reranker 精选到 `top_k`  
**降级：** Cross-Encoder 不可用时 → 启发式打分（关键词重叠 + 精确匹配 + 标题加权）

### 12. Eval 驱动的 Prompt 版本管理

**对应代码：** `src/smart_qa/evaluation/` ✅ 全部实现  
**当前状态：** ✅ `dataset.py`（18 条测试用例，6 个场景）| ✅ `metrics.py`（keyword_recall + summary）| ✅ `runner.py`（CLI: `uv run python -m smart_qa.evaluation.runner`）| ✅ GitLab CI（`.gitlab-ci.yml`，改 Prompt 自动跑评测）| ✅ pre-commit 钩子（提交前快速跑 11 条简单用例）

### 13. Logfire 可观测

**对应代码：** `observability/logfire_setup.py` ✅ 已实现 | `web.py` ✅ 已接入  
**当前状态：** ✅ `logfire.instrument_fastapi()` — API 请求全追踪 | ✅ `logfire.instrument_httpx()` — LLM 调用追踪 | ✅ `logfire.instrument_sqlalchemy()` — 数据库查询耗时 | ✅ `logfire.instrument_pydantic()` — 模型校验日志 | ✅ `logfire.instrument_system_metrics()` — CPU/内存/GC | ✅ `LOGFIRE_TOKEN` 为空时静默跳过，无性能影响

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
| Stream 安全 | ✅ 3.5.2 | ✅ | **完成（input + output 双过滤）** |
| Reranker 接入 | 🟡 8章 P0 | ✅ | **完成（retrieve_k×3 → rerank → top_k）** |
| Eval 自动化 | 🟡 8章 P0 | ✅ | **完成（18 条用例 + CLI + GitLab CI）** |
| Logfire 可观测 | ✅ | ✅ | **完成（FastAPI/SQLAlchemy/httpx/Pydantic 全 instrument）** |
