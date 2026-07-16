<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useAppStore } from '@/stores/app'
import Sidebar from '@/components/Sidebar.vue'
import LoginDialog from '@/components/LoginDialog.vue'

const appStore = useAppStore()

function doLogout() {
  appStore.userId = ''
  appStore.userName = ''
  appStore.userRole = 'user'
  appStore.token = ''
  localStorage.removeItem('smart_qa_token')
  localStorage.removeItem('smart_qa_user')
}
</script>

<template>
  <div class="flex h-screen overflow-hidden">
    <Sidebar />
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- 顶部栏 -->
      <header class="h-10 shrink-0 bg-white border-b border-slate-200 flex items-center justify-end px-4 gap-2">
        <template v-if="appStore.token">
          <span class="text-xs text-slate-500">{{ appStore.userName || appStore.userId }}</span>
          <span v-if="appStore.isAdmin()" class="text-[10px] px-1.5 py-0.5 rounded bg-accent-soft text-accent">管理员</span>
          <button @click="doLogout" class="text-xs text-slate-400 hover:text-red-500 transition-colors">退出</button>
        </template>
        <button v-else @click="appStore.showLogin = true" class="text-xs text-accent hover:underline">登录</button>
      </header>
      <!-- 页面内容 -->
      <main class="flex-1 overflow-hidden">
        <RouterView />
      </main>
    </div>
    <LoginDialog />
  </div>
</template>
