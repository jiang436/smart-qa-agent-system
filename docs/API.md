# API 接口文档

Base URL: `http://localhost:8000/api/v1`

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 普通对话 |
| POST | `/chat/stream` | SSE 流式对话 |
| GET | `/session/{id}/history` | 会话历史 |
| POST | `/approve` | HITL 确认 |
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
| user_id | string | 是 | 用户 ID |
| message | string | 是 | 用户消息 |
| session_id | string | 否 | 会话 ID，空则自动创建 |

### 响应

```json
{
  "answer": "您可以在 App 中设置定时清扫...",
  "session_id": "a1b2c3d4e5f6",
  "intent": "qa"
}
```

### 错误

| 状态码 | 说明 |
|--------|------|
| 429 | 请求过于频繁 |
| 400 | 内容被安全策略拦截 |
| 500 | Agent 执行异常 |

---

## POST /chat/stream

### SSE 事件

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

### 前端示例

```javascript
const response = await fetch('/api/v1/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ user_id: 'U1001', message: '你好' }),
})

const reader = response.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  // 解析 SSE 事件...
}
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

```
POST /api/v1/approve?session_id=xxx&decision=approve&feedback=
```

### 响应

```json
{
  "status": "ok",
  "decision": "approve",
  "feedback": "",
  "context": {}
}
```
