<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()

const navItems = computed(() => {
  const items = [
    { path: '/', label: '智能对话', icon: '💬' },
    { path: '/troubleshoot', label: '故障排查', icon: '🔧' },
    { path: '/consumables', label: '耗材管理', icon: '📦' },
    { path: '/orders', label: '订单追踪', icon: '📮' },
    { path: '/report', label: '使用报告', icon: '📊' },
  ]
  if (appStore.isAdmin()) {
    items.push({ path: '/admin', label: '管理后台', icon: '⚙️' })
  }
  return items
})

const isActive = (path: string) => {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside class="w-52 bg-white border-r border-slate-200 flex flex-col shrink-0">
    <!-- Logo -->
    <div class="px-4 py-4 border-b border-slate-100">
      <div class="flex items-center gap-2">
        <span class="text-xl">🤖</span>
        <div>
          <div class="text-sm font-semibold text-slate-800">Smart QA</div>
          <div class="text-[10px] text-slate-400">智能客服系统</div>
        </div>
      </div>
    </div>

    <!-- Nav -->
    <nav class="flex-1 px-2 py-3 space-y-0.5">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :class="[
          'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors',
          isActive(item.path)
            ? 'bg-accent-soft text-accent font-medium'
            : 'text-slate-600 hover:bg-slate-50 hover:text-slate-800'
        ]"
      >
        <span class="text-base">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

    <!-- Footer -->
    <div class="px-4 py-3 border-t border-slate-100">
      <div class="text-[10px] text-slate-400">v1.0.0 · FastAPI + LangGraph</div>
    </div>
  </aside>
</template>
