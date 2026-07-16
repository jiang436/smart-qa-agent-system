<script setup lang="ts">
import { ref } from 'vue'
import { login, register } from '@/api'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const isRegister = ref(false)
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function submit() {
  errorMsg.value = ''
  if (!username.value.trim() || !password.value.trim()) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  if (isRegister.value && password.value !== confirmPassword.value) {
    errorMsg.value = '两次密码不一致'
    return
  }

  loading.value = true
  try {
    const res = isRegister.value
      ? await register({ username: username.value.trim(), password: password.value, display_name: username.value.trim() })
      : await login({ username: username.value.trim(), password: password.value })

    appStore.userId = res.user_id
    appStore.userName = res.display_name || res.username
    appStore.userRole = res.role as 'user' | 'admin'
    appStore.token = res.token
    localStorage.setItem('smart_qa_token', res.token)
    localStorage.setItem('smart_qa_user', JSON.stringify({ user_id: res.user_id, username: res.username, role: res.role }))
    appStore.showLogin = false
  } catch (e: any) {
    errorMsg.value = e.message || '操作失败'
  } finally {
    loading.value = false
  }
}

function close() {
  appStore.showLogin = false
  errorMsg.value = ''
}

function toggleMode() {
  isRegister.value = !isRegister.value
  errorMsg.value = ''
  confirmPassword.value = ''
}
</script>

<template>
  <Teleport to="body">
    <div v-if="appStore.showLogin" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="close">
      <div class="w-full max-w-sm bg-white rounded-xl shadow-xl border border-slate-200 p-6 mx-4">
        <div class="text-center mb-5">
          <span class="text-3xl">🤖</span>
          <h1 class="text-base font-semibold text-slate-800 mt-1">登录 Smart QA</h1>
        </div>

        <div class="mb-2 p-2.5 bg-blue-50 border border-blue-100 rounded-lg text-xs text-blue-700 text-center leading-relaxed">
          管理员账号密码：<strong>admin</strong> / <strong>admin</strong>
        </div>
        <div class="mb-3 p-2.5 bg-green-50 border border-green-100 rounded-lg text-xs text-green-700 text-center leading-relaxed">
          注册第一个账号自动成为管理员
        </div>

        <form @submit.prevent="submit" class="space-y-3">
          <div>
            <label class="text-xs font-medium text-slate-600 block mb-0.5">用户名</label>
            <input v-model="username" type="text" placeholder="请输入用户名"
              class="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent" />
          </div>
          <div>
            <label class="text-xs font-medium text-slate-600 block mb-0.5">密码</label>
            <input v-model="password" type="password" placeholder="请输入密码"
              class="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent" />
          </div>
          <div v-if="isRegister">
            <label class="text-xs font-medium text-slate-600 block mb-0.5">确认密码</label>
            <input v-model="confirmPassword" type="password" placeholder="请再次输入密码"
              class="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent" />
          </div>

          <p v-if="errorMsg" class="text-xs text-red-500">{{ errorMsg }}</p>

          <button type="submit" :disabled="loading"
            class="w-full py-2 text-sm font-medium text-white bg-accent rounded-lg hover:bg-accent/90 disabled:opacity-50 transition-colors">
            {{ loading ? '处理中...' : isRegister ? '注册并登录' : '登录' }}
          </button>
        </form>

        <div class="mt-3 text-center">
          <button @click="toggleMode" class="text-xs text-accent hover:underline">
            {{ isRegister ? '已有账号？去登录' : '没有账号？去注册' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
