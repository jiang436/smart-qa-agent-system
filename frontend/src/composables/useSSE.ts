import { ref, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAppStore } from '@/stores/app'
import { sendChatStream } from '@/api'
import type { ChatRequest } from '@/api'

export function useSSE() {
  const chat = useChatStore()
  const app = useAppStore()
  const controller = ref<AbortController | null>(null)

  function send(query: string) {
    if (chat.isProcessing) return

    chat.addMessage({ role: 'user', content: query })
    chat.setStage('意图识别')
    const msgId = chat.startStreaming()

    const req: ChatRequest = {
      user_id: app.userId,
      message: query,
      session_id: chat.sessionId || undefined,
    }

    controller.value = sendChatStream(
      req,
      (token) => chat.appendToken(msgId, token),
      (stage) => chat.setStage(stage),
      (intent, sid) => {
        chat.finishStreaming(msgId, intent)
        if (sid) chat.sessionId = sid
        else if (!chat.sessionId) chat.sessionId = crypto.randomUUID()
      },
      (err) => chat.setError(err),
    )
  }

  function abort() {
    controller.value?.abort()
    controller.value = null
    chat.isProcessing = false
  }

  onUnmounted(() => abort())

  return { send, abort, isProcessing: chat.isProcessing }
}
