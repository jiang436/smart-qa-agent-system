import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const userId = ref('U1001')
  const userName = ref('用户')
  const deviceModel = ref('X30 Pro')
  const deviceOnline = ref(true)
  const sidebarCollapsed = ref(false)

  function setUser(id: string, name: string) {
    userId.value = id
    userName.value = name
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    userId, userName, deviceModel, deviceOnline, sidebarCollapsed,
    setUser, toggleSidebar,
  }
})
