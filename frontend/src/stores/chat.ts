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

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const sessionId = ref('')
  const currentIntent = ref('')
  const isProcessing = ref(false)
  const currentStage = ref('')
  const error = ref('')

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
      id, role: 'assistant', content: '', timestamp: Date.now(), isStreaming: true
    })
    return id
  }

  function appendToken(msgId: string, token: string) {
    const msg = messages.value.find(m => m.id === msgId)
    if (msg) msg.content += token
  }

  function finishStreaming(msgId: string, intent?: string, citations?: Citation[]) {
    const msg = messages.value.find(m => m.id === msgId)
    if (msg) {
      msg.isStreaming = false
      if (citations?.length) msg.citations = citations
    }
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

  function clearMessages() {
    messages.value = []
    currentIntent.value = ''
    error.value = ''
  }

  return {
    messages, sessionId, currentIntent, isProcessing, currentStage, error, lastAssistantMsg,
    addMessage, startStreaming, appendToken, finishStreaming, setStage, setError, clearMessages,
  }
})
