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
  if (to.meta.requiresAdmin) {
    const appStore = useAppStore()
    if (!appStore.isAdmin()) {
      next({ name: 'chat' })
      return
    }
  }
  next()
})

export default router
