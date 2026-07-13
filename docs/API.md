# API 接口文档

Base URL: `http://localhost:8000/api/v1`

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 普通对话 |
| POST | `/chat/stream` | SSE 流式对话 |
| GET | `/session/{id}/history` | 会话历史 |
| POST | `/approve` | HITL 确认 |
| GET | `/knowledge/bm25/status` | BM25 索引状态 |
| POST | `/knowledge/bm25/rebuild` | 重建 BM25 索引 |
| POST | `/knowledge/upload` | 上传知识文档（PDF/MD/TXT） |
| POST | `/knowledge/reload` | 重新加载知识库 |
| GET | `/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |
| GET | `/docs` | Swagger UI |

---

## POST /chat

### 请求

```json
{
  "user_id": "U1001",
  "message": "怎么设置定时清扫？",
  "session_id": ""
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 1-64 字符 |
| message | string | 是 | 1-2000 字符 |
| session_id | string | 否 | 空则自动创建 |

### 响应

```json
{
  "answer": "您可以在 App 中设置定时清扫...",
  "session_id": "a1b2c3d4e5f6",
  "intent": "qa"
}
```

### 错误码

| 状态码 | 说明 |
|--------|------|
| 429 | 请求过于频繁 |
| 400 | 内容被安全策略拦截 |
| 422 | 请求体校验不通过（Pydantic） |
| 500 | Agent 执行异常 |

---

## POST /chat/stream

请求体同 `/chat`。返回 SSE 事件流：

```
event: status
data: {"stage":"意图识别","message":"正在理解您的问题..."}

event: token
data: {"text":"定"}
event: token
data: {"text":"时"}

event: citation
data: {"message":"回答基于知识库内容生成"}

event: done
data: {"message":"回答完成","intent":"qa"}
```

---

## GET /session/{session_id}/history

### 响应

```json
{
  "session_id": "a1b2c3",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮您？"}
  ],
  "total": 2
}
```

---

## POST /approve

### 请求

```json
{
  "session_id": "xxx",
  "decision": "approve",
  "feedback": ""
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| decision | string | `approve` / `reject` / `modify` |
| feedback | string | modify 时填写修改意见，最长 500 字符 |

### 响应

```json
{
  "status": "ok",
  "decision": "approve",
  "message": ""
}
```

---

## POST /knowledge/upload

上传知识文档（multipart/form-data）。

| 参数 | 类型 | 说明 |
|------|------|------|
| file | File | PDF / Markdown / TXT，上限 10MB |

### 响应

```json
{
  "status": "ok",
  "file": "产品手册.pdf",
  "chunks": 12,
  "dimension": 512
}
```

## GET /knowledge/bm25/status

### 响应

```json
{
  "status": "ok",
  "doc_count": 921,
  "built_at": "2026-07-13T10:00:00",
  "terms": 4523
}
```

## POST /knowledge/bm25/rebuild

重建 BM25 索引。返回同上。
