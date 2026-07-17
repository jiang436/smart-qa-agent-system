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

export interface Citation { doc_id: string; source: string; matched_sentence: string }

export function sendChatStream(
  req: ChatRequest,
  onToken: (text: string) => void,
  onStatus: (stage: string, message: string) => void,
  onDone: (intent?: string, sessionId?: string, citations?: Citation[]) => void,
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
            else if (event === 'done') onDone(data.intent, data.session_id, data.citations || [])
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

export async function listSessions(userId: string, limit = 20, offset = 0) {
  const params = new URLSearchParams({ user_id: userId, limit: String(limit), offset: String(offset) })
  const res = await fetch(`${BASE}/sessions?${params}`)
  return res.json()
}

export async function deleteSession(sessionId: string) {
  const res = await fetch(`${BASE}/session/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
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

export interface KnowledgeFile {
  filename: string
  file_type: string
  chunks: number
  dimension: number
  uploaded_at: string
  source: string
}

export async function getKnowledgeFiles(): Promise<{ files: KnowledgeFile[] }> {
  const res = await fetch(`${BASE}/knowledge/files`)
  return res.json()
}
