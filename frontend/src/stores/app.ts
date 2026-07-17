import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const userId = ref('U1001')
  const userName = ref('用户')
  const sidebarCollapsed = ref(false)

  function setUser(id: string, name: string) {
    userId.value = id
    userName.value = name
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    userId, userName, sidebarCollapsed,
    setUser, toggleSidebar,
  }
})
