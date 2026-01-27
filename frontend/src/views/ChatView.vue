<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSSE } from '@/composables/useSSE'
import StatusPulse from '@/components/StatusPulse.vue'
import MessageBubble from '@/components/MessageBubble.vue'

const chat = useChatStore()
const { send, abort } = useSSE()

const input = ref('')
const messagesEl = ref<HTMLElement>()

function scrollToBottom() {
  nextTick(() => {
    const el = messagesEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(() => chat.messages.length, scrollToBottom)
watch(() => chat.lastAssistantMsg?.content, scrollToBottom)

function onSubmit() {
  const text = input.value.trim()
  if (!text || chat.isProcessing) return
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

const quickActions = [
  { label: '怎么设置定时清扫', intent: 'qa' },
  { label: '机器不工作了怎么办', intent: 'troubleshoot' },
  { label: '边刷该换了', intent: 'consumables' },
  { label: 'X30 Pro 参数规格', intent: 'qa' },
]
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <header class="flex items-center justify-between px-5 py-3 bg-white border-b border-slate-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-slate-800">智能对话</h1>
        <p class="text-[11px] text-slate-400">{{ chat.currentStage || '就绪' }}</p>
      </div>
      <div class="flex items-center gap-3">
        <StatusPulse />
        <button
          @click="chat.clearMessages()"
          class="text-[11px] text-slate-400 hover:text-slate-600 transition-colors"
        >清空对话</button>
      </div>
    </header>

    <!-- Messages -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-5 py-4 space-y-4">
      <!-- Empty state -->
      <div v-if="chat.messages.length === 0" class="flex flex-col items-center justify-center h-full text-center">
        <div class="text-5xl mb-4">🤖</div>
        <h2 class="text-lg font-semibold text-slate-700 mb-1">智能问答助手</h2>
        <p class="text-sm text-slate-400 mb-6 max-w-sm">
          我是您的智能家居客服，可以帮您解答产品使用问题、排查设备故障、管理耗材更换。
        </p>
        <div class="grid grid-cols-2 gap-2 max-w-sm">
          <button
            v-for="action in quickActions"
            :key="action.label"
            @click="onQuickAction(action.label)"
            class="text-left px-3 py-2 rounded-md border border-slate-200 text-xs text-slate-600 hover:border-accent hover:text-accent hover:bg-accent-soft/30 transition-colors"
          >
            {{ action.label }}
          </button>
        </div>
      </div>

      <!-- Messages -->
      <MessageBubble v-for="msg in chat.messages" :key="msg.id" :msg="msg" />

      <!-- Error -->
      <div v-if="chat.error" class="p-3 bg-danger/5 border border-danger/20 rounded-md text-sm text-danger">
        {{ chat.error }}
        <button @click="chat.error = ''" class="ml-2 underline">关闭</button>
      </div>
    </div>

    <!-- Input -->
    <div class="px-5 py-3 bg-white border-t border-slate-200 shrink-0">
      <div class="flex items-end gap-2">
        <div class="flex-1 relative">
          <textarea
            v-model="input"
            @keydown="onKeydown"
            :disabled="chat.isProcessing"
            placeholder="输入您的问题… (Enter 发送, Shift+Enter 换行)"
            rows="1"
            class="w-full resize-none rounded-md border border-slate-200 px-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent-soft disabled:bg-slate-50"
          />
        </div>
        <button
          v-if="chat.isProcessing"
          @click="abort"
          class="flex items-center justify-center w-9 h-9 rounded-md bg-danger text-white hover:bg-danger/90 transition-colors shrink-0"
          title="停止生成"
        >
          <span class="text-xs">■</span>
        </button>
        <button
          v-else
          @click="onSubmit"
          :disabled="!input.trim()"
          class="flex items-center justify-center w-9 h-9 rounded-md bg-accent text-white hover:bg-accent/90 disabled:opacity-40 transition-colors shrink-0"
          title="发送"
        >
          <span class="text-sm">↑</span>
        </button>
      </div>
    </div>
  </div>
</template>
