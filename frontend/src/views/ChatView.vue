<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSSE } from '@/composables/useSSE'
import MessageBubble from '@/components/MessageBubble.vue'
import TypingIndicator from '@/components/TypingIndicator.vue'
import SkeletonMessage from '@/components/SkeletonMessage.vue'
import ErrorBanner from '@/components/ErrorBanner.vue'

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

const quickActions = [
  { label: 'X30 Pro 参数规格', icon: 'search' },
  { label: '设备故障怎么排查', icon: 'wrench' },
  { label: '边刷该换什么型号', icon: 'package' },
  { label: '怎么设置定时清扫', icon: 'clock' },
]
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <header class="flex items-center justify-between px-6 py-3 bg-surface border-b border-neutral-200 shrink-0">
      <div class="flex items-center gap-3">
        <div>
          <h1 class="text-sm font-semibold text-neutral-800">智能对话</h1>
          <p class="text-[11px] text-neutral-400 mt-0.5">
            <span v-if="chat.isProcessing" class="text-accent">{{ chat.currentStage }}</span>
            <span v-else>就绪 - 随时为您解答</span>
          </p>
        </div>
      </div>
      <button
        @click="chat.clearMessages()"
        class="text-[11px] text-neutral-400 hover:text-neutral-600 transition-base"
      >清空对话</button>
    </header>

    <!-- Messages -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto">
      <!-- Empty state -->
      <div v-if="chat.messages.length === 0" class="flex flex-col items-center justify-center min-h-full px-6 py-16 text-center">
        <div class="w-16 h-16 rounded-2xl bg-accent-soft flex items-center justify-center mb-6">
          <svg class="w-8 h-8 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
          </svg>
        </div>
        <h2 class="text-lg font-semibold text-neutral-800 mb-2">智能问答助手</h2>
        <p class="text-sm text-neutral-400 max-w-prose mb-8 leading-relaxed">
          我是您的智能家居客服，可以帮您解答产品使用问题、排查设备故障、管理耗材更换。
        </p>
        <div class="grid grid-cols-2 gap-2.5 max-w-md w-full">
          <button
            v-for="action in quickActions"
            :key="action.label"
            @click="input = action.label; onSubmit()"
            class="text-left px-4 py-3 rounded-lg border border-neutral-200 text-sm text-neutral-600 hover:border-accent-muted hover:text-accent hover:bg-accent-soft/30 transition-base group"
          >
            {{ action.label }}
          </button>
        </div>
      </div>

      <!-- Message list -->
      <div v-else class="px-6 py-5 space-y-5 max-w-3xl mx-auto">
        <MessageBubble v-for="msg in chat.messages" :key="msg.id" :msg="msg" />

        <!-- Skeleton loading while waiting for first token -->
        <SkeletonMessage v-if="chat.isProcessing && !chat.lastAssistantMsg?.content" />

        <!-- Error banner -->
        <ErrorBanner v-if="chat.error" :message="chat.error" @dismiss="chat.error = ''" />
      </div>
    </div>

    <!-- Input bar -->
    <div class="px-6 py-4 bg-surface border-t border-neutral-200 shrink-0">
      <div class="max-w-3xl mx-auto">
        <div class="flex items-end gap-2.5">
          <div class="flex-1 relative">
            <textarea
              v-model="input"
              @keydown="onKeydown"
              :disabled="chat.isProcessing"
              placeholder="输入您的问题..."
              rows="1"
              class="w-full resize-none rounded-lg border border-neutral-200 bg-bg-primary px-4 py-2.5 text-sm placeholder:text-neutral-400 focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft disabled:opacity-50 transition-base"
            />
          </div>
          <!-- Stop button -->
          <button
            v-if="chat.isProcessing"
            @click="abort"
            class="flex items-center justify-center w-10 h-10 rounded-lg bg-danger text-white hover:bg-red-700 transition-base shrink-0"
            title="停止生成"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1" /></svg>
          </button>
          <!-- Send button -->
          <button
            v-else
            @click="onSubmit"
            :disabled="!input.trim()"
            class="flex items-center justify-center w-10 h-10 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed transition-base shrink-0"
            title="发送 (Enter)"
          >
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          </button>
        </div>
        <p class="text-[10px] text-neutral-400 mt-2 text-center">Enter 发送 · Shift+Enter 换行</p>
      </div>
    </div>
  </div>
</template>
