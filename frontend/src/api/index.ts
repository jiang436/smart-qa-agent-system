const BASE = '/api/v1'

export interface ChatRequest {
  user_id: string
  message: string
  session_id?: string
}

export interface ChatResponse {
  answer: string
  session_id: string
  intent: string
}

// ── Auth ──

export interface AuthRequest {
  username: string
  password: string
}

export interface AuthResponse {
  token: string
  user_id: string
  username: string
  role: string
  display_name: string
}

export interface UserInfo {
  user_id: string
  username: string
  role: string
  display_name: string
}

export async function login(req: AuthRequest): Promise<AuthResponse> {
  const r = await fetch(`${BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error((await r.json()).detail || '登录失败')
  return r.json()
}

export async function register(req: AuthRequest & { display_name?: string }): Promise<AuthResponse> {
  const r = await fetch(`${BASE}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error((await r.json()).detail || '注册失败')
  return r.json()
}

export async function logout(token: string): Promise<void> {
  await fetch(`${BASE}/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
}

export async function getUserInfo(token: string): Promise<UserInfo> {
  const r = await fetch(`${BASE}/user/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!r.ok) throw new Error('获取用户信息失败')
  return r.json()
}


export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  return res.json()
}

export function sendChatStream(
  req: ChatRequest,
  onToken: (text: string) => void,
  onStatus: (stage: string, message: string) => void,
  onDone: (intent?: string, sessionId?: string) => void,
  onError: (err: string) => void,
): AbortController {
  const controller = new AbortController()

  fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) {
      onError(`HTTP ${response.status}`)
      return
    }
    const reader = response.body?.getReader()
    if (!reader) { onError('无法读取响应流'); return }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let event = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          event = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (event === 'token') onToken(data.text || '')
            else if (event === 'status') onStatus(data.stage || '', data.message || '')
            else if (event === 'done') onDone(data.intent, data.session_id)
            else if (event === 'error') onError(data.message || '未知错误')
          } catch { /* skip malformed */ }
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') onError(err.message)
  })

  return controller
}


export async function getSessionHistory(sessionId: string) {
  const res = await fetch(`${BASE}/session/${sessionId}/history`)
  return res.json()
}

export async function approveAction(sessionId: string, decision: string, feedback = '') {
  const form = new URLSearchParams({ session_id: sessionId, decision, feedback })
  const res = await fetch(`${BASE}/approve`, { method: 'POST', body: form })
  return res.json()
}

// ── Knowledge ──

export interface KnowledgeStatus {
  status: string
  collection?: string
  total_documents?: number
  dimension?: number
  message?: string
}

export async function getKnowledgeStatus(): Promise<KnowledgeStatus> {
  const res = await fetch(`${BASE}/knowledge/status`)
  return res.json()
}

export async function uploadKnowledgeFile(file: File, onProgress?: (pct: number) => void): Promise<any> {
  const form = new FormData()
  form.append('file', file)

  const xhr = new XMLHttpRequest()
  return new Promise((resolve, reject) => {
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText))
      else reject(new Error(JSON.parse(xhr.responseText).detail || '上传失败'))
    }
    xhr.onerror = () => reject(new Error('网络错误'))
    xhr.open('POST', `${BASE}/knowledge/upload`)
    xhr.send(form)
  })
}

export async function reloadKnowledge(): Promise<any> {
  const res = await fetch(`${BASE}/knowledge/reload`, { method: 'POST' })
  return res.json()
}

export async function getBm25Status(): Promise<any> {
  const res = await fetch(`${BASE}/knowledge/bm25/status`)
  return res.json()
}

export async function rebuildBm25(): Promise<any> {
  const res = await fetch(`${BASE}/knowledge/bm25/rebuild`, { method: 'POST' })
  return res.json()
}

// ── Orders ──

export interface LogisticsEventItem {
  event_type: string
  message: string
  location: string | null
  timestamp: string
}

export interface OrderItem {
  order_id: string
  user_id: string
  part_type: string
  part_name: string
  quantity: number
  price: number
  status: string
  tracking_number: string | null
  express_company: string | null
  shipping_address: string
  created_at: string
  updated_at: string
  logistics: LogisticsEventItem[]
}

export interface OrderListResponse {
  orders: OrderItem[]
  total: number
}

export interface OrderStatusResponse {
  order_id: string
  status: string
  status_label: string
  tracking_number: string | null
  express_company: string | null
  logistics: LogisticsEventItem[]
}

export async function getOrders(userId: string, page = 1): Promise<OrderListResponse> {
  const r = await fetch(`${BASE}/orders?user_id=${userId}&page=${page}&page_size=20`)
  return r.json()
}

export async function getOrderDetail(orderId: string): Promise<OrderStatusResponse> {
  const r = await fetch(`${BASE}/orders/${orderId}`)
  return r.json()
}

export async function advanceOrder(orderId: string, scenario = 'normal'): Promise<OrderStatusResponse> {
  const r = await fetch(`${BASE}/orders/${orderId}/advance?scenario=${scenario}`, { method: 'POST' })
  return r.json()
}

export async function deleteOrder(orderId: string): Promise<{ status: string; message: string }> {
  const r = await fetch(`${BASE}/orders/${orderId}`, { method: 'DELETE' })
  return r.json()
}

// ── Search Logs ──

export interface SearchLogEntry {
  id: number
  session_id: string
  user_id: string
  query: string
  intent: string
  answer_length: number
  duration_ms: number
  source: string
  created_at: string
}

export interface SearchLogsResponse {
  total: number
  page: number
  page_size: number
  logs: SearchLogEntry[]
}

export async function getSearchLogs(page = 1, pageSize = 20): Promise<SearchLogsResponse> {
  const res = await fetch(`${BASE}/search/logs?page=${page}&page_size=${pageSize}`)
  return res.json()
}

export async function submitFeedback(searchLogId: number, userId: string, action: string, detail = '') {
  const params = new URLSearchParams({ search_log_id: String(searchLogId), user_id: userId, action, detail })
  const res = await fetch(`${BASE}/search/feedback`, { method: 'POST', body: params })
  return res.json()
}

// ── Sessions ──

export interface SessionSummary {
  session_id: string
  user_id: string
  intent: string
  message_count: number
  preview: string
  updated_at: string
  created_at: string
}

export interface SessionsResponse {
  total: number
  page: number
  page_size: number
  sessions: SessionSummary[]
}

export async function getSessions(page = 1, pageSize = 50): Promise<SessionsResponse> {
  const res = await fetch(`${BASE}/sessions?page=${page}&page_size=${pageSize}`)
  return res.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE}/session/${sessionId}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '删除会话失败')
  }
}
