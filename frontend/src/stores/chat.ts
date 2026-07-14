import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  intent?: string
  citations?: Citation[]
  timestamp: number
  isStreaming?: boolean
}

export interface Citation {
  doc_id: string
  source: string
  matched_sentence: string
}

export interface SessionItem {
  session_id: string
  user_id: string
  intent: string
  message_count: number
  preview: string
  updated_at: string
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const sessionId = ref('')
  const currentIntent = ref('')
  const isProcessing = ref(false)
  const currentStage = ref('')
  const error = ref('')
  const sessions = ref<SessionItem[]>([])
  const sessionsTotal = ref(0)

  const lastAssistantMsg = computed(() => {
    const msgs = messages.value
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant') return msgs[i]
    }
    return null
  })

  function addMessage(msg: Omit<Message, 'id' | 'timestamp'>) {
    const id = crypto.randomUUID()
    messages.value.push({ ...msg, id, timestamp: Date.now() })
    return id
  }

  function startStreaming() {
    isProcessing.value = true
    error.value = ''
    const id = crypto.randomUUID()
    messages.value.push({
      id, role: 'assistant', content: '', timestamp: Date.now(), isStreaming: true,
    })
    return id
  }

  function appendToken(msgId: string, token: string) {
    const msg = messages.value.find(m => m.id === msgId)
    if (msg) msg.content += token
  }

  function finishStreaming(msgId: string, intent?: string) {
    const msg = messages.value.find(m => m.id === msgId)
    if (msg) msg.isStreaming = false
    isProcessing.value = false
    if (intent) currentIntent.value = intent
  }

  function setStage(stage: string) {
    currentStage.value = stage
  }

  function setError(err: string) {
    error.value = err
    isProcessing.value = false
  }

  function loadMessages(msgs: Message[]) {
    messages.value = msgs
  }

  function clearMessages() {
    messages.value = []
    currentIntent.value = ''
    error.value = ''
    sessionId.value = ''
  }

  function setSessions(list: SessionItem[], total: number) {
    sessions.value = list
    sessionsTotal.value = total
  }

  return {
    messages, sessionId, currentIntent, isProcessing, currentStage, error,
    sessions, sessionsTotal, lastAssistantMsg,
    addMessage, startStreaming, appendToken, finishStreaming,
    setStage, setError, loadMessages, clearMessages, setSessions,
  }
})
