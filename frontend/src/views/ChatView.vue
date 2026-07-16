<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAppStore } from '@/stores/app'
import { useSSE } from '@/composables/useSSE'
import { getSessionHistory, getSessions, deleteSession } from '@/api'
import StatusPulse from '@/components/StatusPulse.vue'
import MessageBubble from '@/components/MessageBubble.vue'

const chat = useChatStore()
const { send, abort } = useSSE()

const input = ref('')
const messagesEl = ref<HTMLElement>()
const sidebarOpen = ref(false)
const sessionsLoading = ref(false)

async function fetchSessions() {
  sessionsLoading.value = true
  try {
    const res = await getSessions(1, 50)
    chat.setSessions(res.sessions, res.total)
  } catch { /* ignore */ }
  sessionsLoading.value = false
}

onMounted(() => {
  fetchSessions()
})

async function loadSession(sid: string) {
  try {
    const res = await getSessionHistory(sid)
    const msgs = (res.messages || []).map((m: any) => ({
      id: crypto.randomUUID(),
      role: normalizeRole(m.role || 'user'),
      content: m.content || '',
      timestamp: Date.now(),
    }))
    chat.loadMessages(msgs)
    chat.sessionId = sid
    sidebarOpen.value = false
  } catch { /* ignore */ }
}

function normalizeRole(role: string): string {
  /* 兼容后端可能返回的 'human'/'ai' */
  const map: Record<string, string> = { human: 'user', ai: 'assistant' }
  return map[role] || role
}

async function handleDelete(sid: string) {
  try {
    await deleteSession(sid)
    // 如果删除的是当前会话，清空消息区
    if (chat.sessionId === sid) {
      chat.clearMessages()
    }
    // 刷新列表
    await fetchSessions()
  } catch { /* ignore */ }
}

const quickActions = [
  { label: '怎么设置定时清扫', intent: 'qa' },
  { label: '机器不工作了怎么办', intent: 'troubleshoot' },
  { label: '边刷该换了', intent: 'consumables' },
  { label: 'X30 Pro 参数规格', intent: 'qa' },
]

const intentLabel: Record<string, string> = {
  qa: '问答', troubleshoot: '故障', consumables: '耗材', device_control: '设备', report: '报告', general: '其他',
}

function newChat() {
  chat.clearMessages()
  sidebarOpen.value = false
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(() => chat.messages.length, scrollToBottom)

function onSubmit() {
  const text = input.value.trim()
  if (!text || chat.isProcessing) return
  if (!localStorage.getItem('smart_qa_token')) {
    useAppStore().showLogin = true
    return
  }
  input.value = ''
  send(text)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSubmit()
  }
}

function onQuickAction(label: string) {
  input.value = label
  onSubmit()
}
</script>
<template>
  <div class="flex h-full">
    <!-- Session sidebar -->
    <Transition name="slide">
      <div v-if="sidebarOpen" class="w-64 bg-white border-r border-slate-200 flex flex-col shrink-0">
        <div class="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <h2 class="text-xs font-semibold text-slate-500 uppercase">历史会话</h2>
          <div class="flex items-center gap-2">
            <button @click="fetchSessions" class="text-[11px] text-accent hover:underline">刷新</button>
            <button @click="newChat" class="text-[11px] text-accent hover:underline">新对话</button>
          </div>
        </div>
        <div v-if="sessionsLoading" class="p-4 text-xs text-slate-400">加载中…</div>
        <div v-else class="flex-1 overflow-y-auto">
          <div
            v-for="s in chat.sessions" :key="s.session_id"
            @click="loadSession(s.session_id)"
            :class="[
              'group relative px-4 py-3 border-b border-slate-50 cursor-pointer hover:bg-slate-50 transition-colors',
              s.session_id === chat.sessionId ? 'bg-accent-soft/20 border-l-2 border-l-accent' : ''
            ]"
          >
            <button
              @click.stop="handleDelete(s.session_id)"
              class="absolute top-2 right-2 w-5 h-5 flex items-center justify-center rounded text-[11px] text-slate-300 hover:text-danger hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-opacity"
              title="删除会话"
            >×</button>
            <div class="flex items-center gap-2 mb-1">
              <span class="px-1 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-500">{{ intentLabel[s.intent] || s.intent }}</span>
              <span class="text-[10px] text-slate-400">{{ s.message_count }}条</span>
            </div>
            <p class="text-xs text-slate-600 truncate">{{ s.preview || '（空）' }}</p>
            <p class="text-[10px] text-slate-400 mt-1">{{ s.updated_at?.slice(0, 16)?.replace('T', ' ') || '' }}</p>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Main chat area -->
    <div class="flex flex-col flex-1 min-w-0">
      <!-- Header -->
      <header class="flex items-center justify-between px-5 py-3 bg-white border-b border-slate-200 shrink-0">
        <div class="flex items-center gap-3">
          <button @click="sidebarOpen = !sidebarOpen" class="text-slate-500 hover:text-slate-700 text-sm">☰</button>
          <span class="text-sm font-semibold text-slate-800">智能对话</span>
          <StatusPulse />
        </div>
      </header>

      <!-- Messages -->
      <div ref="messagesEl" class="flex-1 overflow-y-auto p-5 space-y-4">
        <div v-if="chat.messages.length === 0" class="flex flex-col items-center justify-center h-full text-slate-400">
          <span class="text-5xl mb-3">💬</span>
          <p class="text-sm">有什么可以帮您的？</p>
        </div>
        <MessageBubble v-for="msg in chat.messages" :key="msg.id" :msg="msg" />
      </div>

      <!-- Quick actions -->
      <div v-if="chat.messages.length === 0 && quickActions.length" class="px-5 py-2 flex gap-2 overflow-x-auto shrink-0">
        <button
          v-for="(act, i) in quickActions" :key="i"
          @click="onQuickAction(act.label)"
          class="shrink-0 px-3 py-1.5 text-xs rounded-full border border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-accent hover:text-accent transition-colors"
        >{{ act.label }}</button>
      </div>

      <!-- Input -->
      <div class="px-5 py-3 bg-white border-t border-slate-200 shrink-0">
        <div class="flex items-center gap-2">
          <div class="flex-1 flex items-center">
            <textarea
              v-model="input"
              @keydown="onKeydown"
              :disabled="chat.isProcessing"
              placeholder="输入您的问题… (Enter 发送, Shift+Enter 换行)"
              rows="1"
              class="w-full resize-none rounded-md border border-slate-200 px-3 py-2 text-sm leading-5 placeholder:text-slate-400 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent-soft disabled:bg-slate-50"
            />
          </div>
          <button
            v-if="chat.isProcessing"
            @click="abort"
            class="flex items-center justify-center w-9 h-9 rounded-md bg-danger text-white hover:bg-danger/90 transition-colors shrink-0"
            title="停止生成"
          ><span class="text-xs">■</span></button>
          <button
            v-else
            @click="onSubmit"
            :disabled="!input.trim()"
            class="flex items-center justify-center w-9 h-9 rounded-md bg-accent text-white hover:bg-accent/90 disabled:opacity-40 transition-colors shrink-0"
            title="发送"
          ><span class="text-sm">↑</span></button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.slide-enter-from, .slide-leave-to { transform: translateX(-100%); opacity: 0; }
</style>
