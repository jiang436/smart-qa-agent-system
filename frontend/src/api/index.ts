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
