/**
 * App Store 测试 — 用户信息、侧边栏状态
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppStore } from '../../src/stores/app'

describe('AppStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('default values', () => {
    it('has default userId', () => {
      const store = useAppStore()
      expect(store.userId).toBe('U1001')
    })

    it('has default userName', () => {
      const store = useAppStore()
      expect(store.userName).toBe('用户')
    })

    it('sidebar is expanded by default', () => {
      const store = useAppStore()
      expect(store.sidebarCollapsed).toBe(false)
    })
  })

  describe('setUser', () => {
    it('updates userId and userName', () => {
      const store = useAppStore()
      store.setUser('U2002', '测试用户')
      expect(store.userId).toBe('U2002')
      expect(store.userName).toBe('测试用户')
    })
  })

  describe('toggleSidebar', () => {
    it('toggles sidebarCollapsed', () => {
      const store = useAppStore()
      expect(store.sidebarCollapsed).toBe(false)
      store.toggleSidebar()
      expect(store.sidebarCollapsed).toBe(true)
      store.toggleSidebar()
      expect(store.sidebarCollapsed).toBe(false)
    })
  })
})
