<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()
const app = useAppStore()

interface SessionEntry {
  id: string
  title: string
  timestamp: number
}

const sessions = ref<SessionEntry[]>([])

function loadSessions() {
  try {
    sessions.value = JSON.parse(localStorage.getItem('qa_sessions') || '[]')
  } catch {
    sessions.value = []
  }
}

loadSessions()

// 当 chat.sessionId 变化时刷新列表
watch(() => chat.sessionId, () => {
  loadSessions()
})

function isActive(sid: string) {
  return chat.sessionId === sid
}

function selectSession(sid: string) {
  router.push('/')
  chat.sessionId = sid
}

function startNewChat() {
  chat.clearMessages()
  router.push('/')
}

function deleteSession(sid: string) {
  sessions.value = sessions.value.filter(s => s.id !== sid)
  localStorage.setItem('qa_sessions', JSON.stringify(sessions.value))
  if (chat.sessionId === sid) {
    chat.clearMessages()
  }
}

function formatTime(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60_000) return '刚刚'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3600_000)} 小时前`
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return new Date(ts).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <aside class="w-56 bg-surface border-r border-neutral-200 flex flex-col shrink-0">
    <!-- Logo -->
    <div class="px-5 py-4 border-b border-neutral-100">
      <div class="flex items-center gap-2.5">
        <div class="w-7 h-7 rounded-md bg-accent flex items-center justify-center">
          <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
          </svg>
        </div>
        <div class="leading-tight">
          <div class="text-sm font-semibold text-neutral-800">Smart QA</div>
          <div class="text-[11px] text-neutral-400">智能问答系统</div>
        </div>
      </div>
    </div>

    <!-- New Chat -->
    <div class="px-3 pt-3 pb-2">
      <button
        @click="startNewChat"
        class="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover transition-base"
      >
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
        新建对话
      </button>
    </div>

    <!-- Session list -->
    <nav class="flex-1 overflow-y-auto px-3 py-2 space-y-0.5">
      <template v-if="sessions.length > 0">
        <div
          v-for="s in sessions"
          :key="s.id"
          @click="selectSession(s.id)"
          :class="[
            'group flex items-center gap-2 px-3 py-2.5 rounded-md cursor-pointer transition-base',
            isActive(s.id)
              ? 'bg-accent-soft text-accent font-medium'
              : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-800'
          ]"
        >
          <svg class="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
          </svg>
          <div class="flex-1 min-w-0">
            <div class="text-xs truncate">{{ s.title }}</div>
            <div class="text-[10px] opacity-60 mt-0.5">{{ formatTime(s.timestamp) }}</div>
          </div>
          <button
            @click.stop="deleteSession(s.id)"
            class="shrink-0 w-5 h-5 rounded opacity-0 group-hover:opacity-100 hover:bg-red-100 hover:text-red-500 text-neutral-400 flex items-center justify-center transition-base"
            title="删除"
          >
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </template>

      <!-- Empty state -->
      <div v-else class="flex flex-col items-center justify-center py-12 text-center">
        <svg class="w-8 h-8 text-neutral-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
          <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
        </svg>
        <p class="text-xs text-neutral-400">暂无对话记录</p>
        <p class="text-[10px] text-neutral-400 mt-1">点击上方开始新对话</p>
      </div>
    </nav>

    <!-- Bottom: Admin + footer -->
    <div class="border-t border-neutral-100">
      <router-link
        to="/admin"
        :class="[
          'flex items-center gap-2.5 mx-3 mt-2 px-3 py-2 rounded-md text-xs transition-base',
          route.path === '/admin'
            ? 'bg-accent-soft text-accent font-medium'
            : 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700'
        ]"
      >
        <svg class="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        管理后台
      </router-link>
      <div class="px-5 py-3">
        <div class="text-[10px] text-neutral-400">v1.0.0 — Smart QA</div>
      </div>
    </div>
  </aside>
</template>
