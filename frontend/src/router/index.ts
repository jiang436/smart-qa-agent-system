import { createRouter, createWebHistory } from 'vue-router'
import { useAppStore } from '@/stores/app'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
    },
    {
      path: '/troubleshoot',
      name: 'troubleshoot',
      component: () => import('@/views/TroubleshootView.vue'),
    },
    {
      path: '/consumables',
      name: 'consumables',
      component: () => import('@/views/ConsumablesView.vue'),
    },
    {
      path: '/orders',
      name: 'orders',
      component: () => import('@/views/OrderTrackView.vue'),
    },
    {
      path: '/report',
      name: 'report',
      component: () => import('@/views/ReportView.vue'),
    },
    {
      path: '/admin',
      name: 'admin',
      meta: { requiresAdmin: true },
      component: () => import('@/views/AdminView.vue'),
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const appStore = useAppStore()
  if (!appStore.token) {
    const savedToken = localStorage.getItem('smart_qa_token')
    const savedUser = localStorage.getItem('smart_qa_user')
    if (savedToken && savedUser) {
      try {
        const u = JSON.parse(savedUser)
        appStore.setUser(u.user_id || '', u.username || '', (u.role as 'user' | 'admin') || 'user', savedToken)
      } catch {
        localStorage.removeItem('smart_qa_token')
        localStorage.removeItem('smart_qa_user')
      }
    }
  }
  if (to.meta.requiresAdmin && !appStore.isAdmin()) {
    next({ name: 'chat' })
    return
  }
  next()
})

export default router
