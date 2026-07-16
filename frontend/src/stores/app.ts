import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const userId = ref('')
  const userName = ref('')
  const userRole = ref<'user' | 'admin'>('user')
  const deviceModel = ref('X30 Pro')
  const deviceOnline = ref(true)
  const sidebarCollapsed = ref(false)
  const token = ref('')
  const showLogin = ref(false)

  function setUser(id: string, name: string, role: 'user' | 'admin' = 'user', t: string = '') {
    userId.value = id
    userName.value = name
    userRole.value = role
    if (t) token.value = t
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function isAdmin() {
    return userRole.value === 'admin'
  }

  return {
    userId, userName, userRole, deviceModel, deviceOnline, sidebarCollapsed, token, showLogin,
    setUser, toggleSidebar, isAdmin,
  }
})
