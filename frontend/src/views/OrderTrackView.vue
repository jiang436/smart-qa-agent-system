<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { getOrders, getOrderDetail, advanceOrder, deleteOrder } from '@/api'
import type { OrderItem, LogisticsEventItem, OrderStatusResponse } from '@/api'

const app = useAppStore()
const orders = ref<OrderItem[]>([])
const total = ref(0)
const loading = ref(false)
const selectedOrder = ref<OrderStatusResponse | null>(null)
const detailLoading = ref(false)
const errorMsg = ref('')

const statusColors: Record<string, string> = {
  pending: 'bg-slate-100 text-slate-600',
  confirmed: 'bg-blue-100 text-blue-600',
  paid: 'bg-blue-100 text-blue-600',
  processing: 'bg-yellow-100 text-yellow-600',
  shipped: 'bg-indigo-100 text-indigo-600',
  in_transit: 'bg-purple-100 text-purple-600',
  delivered: 'bg-green-100 text-green-600',
  out_of_stock: 'bg-red-100 text-red-600',
  damaged: 'bg-orange-100 text-orange-600',
  lost: 'bg-red-100 text-red-600',
  returned: 'bg-amber-100 text-amber-600',
  refunded: 'bg-slate-100 text-slate-500',
}

const statusLabels: Record<string, string> = {
  pending: '待确认', confirmed: '已确认', paid: '已付款', processing: '备货中',
  shipped: '已发货', in_transit: '运输中', delivered: '已签收',
  out_of_stock: '缺货', damaged: '货物损坏', lost: '物流丢失',
  returned: '退货中', refunded: '已退款',
}

const eventIcons: Record<string, string> = {
  scan: '📋', shipped: '📦', location_update: '🚚',
  delivery_attempt: '🏠', delayed: '⏳', out_of_stock: '⚠️',
  damaged: '💔', lost: '🔍', returned: '↩️', delivered: '✅',
}

async function fetchOrders() {
  if (!app.userId) return
  loading.value = true
  try {
    const res = await getOrders(app.userId)
    orders.value = res.orders
    total.value = res.total
  } catch {
    orders.value = []
  }
  loading.value = false
}

async function showDetail(orderId: string) {
  detailLoading.value = true
  errorMsg.value = ''
  try {
    selectedOrder.value = await getOrderDetail(orderId)
  } catch {
    errorMsg.value = '获取订单详情失败'
    selectedOrder.value = null
  }
  detailLoading.value = false
}

async function handleAdvance(orderId: string) {
  detailLoading.value = true
  try {
    selectedOrder.value = await advanceOrder(orderId)
    const idx = orders.value.findIndex(o => o.order_id === orderId)
    if (idx >= 0) {
      orders.value[idx].status = selectedOrder.value.status
    }
  } catch {
    errorMsg.value = '推进物流失败'
  }
  detailLoading.value = false
}

async function handleDelete(orderId: string) {
  if (!confirm('确定删除此订单？物流记录也会一并清除。')) return
  try {
    await deleteOrder(orderId)
    closeDetail()
    fetchOrders()
  } catch {
    errorMsg.value = '删除失败'
  }
}

function closeDetail() {
  selectedOrder.value = null
}

onMounted(fetchOrders)
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center justify-between px-5 py-3 bg-white border-b border-slate-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-slate-800">订单管理</h1>
        <p class="text-[11px] text-slate-400">耗材订单与物流追踪（模拟数据）</p>
      </div>
      <button @click="fetchOrders" class="text-xs text-accent hover:underline">刷新</button>
    </header>

    <div v-if="loading" class="flex-1 flex items-center justify-center text-xs text-slate-400">加载中…</div>

    <div v-else-if="orders.length === 0" class="flex-1 flex flex-col items-center justify-center text-slate-400">
      <span class="text-4xl mb-2">📭</span>
      <p class="text-sm">暂无订单</p>
      <p class="text-xs mt-1">去耗材页面购买配件后，订单会出现在这里</p>
    </div>

    <div v-else class="flex-1 overflow-y-auto p-5 space-y-3">
      <div
        v-for="order in orders" :key="order.order_id"
        @click="showDetail(order.order_id)"
        class="bg-white rounded-lg border border-slate-200 p-4 cursor-pointer hover:border-accent hover:shadow-sm transition-all"
      >
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-medium text-slate-700">{{ order.part_name }} × {{ order.quantity }}</span>
          <span class="px-2 py-0.5 rounded text-[10px] font-medium" :class="statusColors[order.status] || 'bg-slate-100 text-slate-500'">
            {{ statusLabels[order.status] || order.status }}
          </span>
        </div>
        <div class="flex items-center justify-between text-[11px] text-slate-400">
          <span>¥{{ order.price }}</span>
          <span>{{ order.order_id }}</span>
          <span>{{ order.created_at?.slice(0, 10) }}</span>
        </div>
        <div v-if="order.express_company" class="mt-1.5 text-[11px] text-slate-400">
          📮 {{ order.express_company }} {{ order.tracking_number }}
        </div>
      </div>
    </div>

    <!-- 订单详情弹窗 -->
    <Teleport to="body">
      <div v-if="selectedOrder" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="closeDetail">
        <div class="w-full max-w-lg bg-white rounded-xl shadow-xl border border-slate-200 mx-4 max-h-[80vh] flex flex-col">
          <!-- 弹窗标题 -->
          <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100 shrink-0">
            <div>
              <h2 class="text-sm font-semibold text-slate-800">订单详情</h2>
              <p class="text-[11px] text-slate-400">{{ selectedOrder.order_id }}</p>
            </div>
            <button @click="closeDetail" class="text-slate-400 hover:text-slate-600 text-lg leading-none">✕</button>
          </div>

          <div class="flex-1 overflow-y-auto p-5 space-y-4">
            <!-- 状态 -->
            <div class="flex items-center justify-between">
              <span class="text-xs text-slate-500">当前状态</span>
              <span class="px-2.5 py-1 rounded text-xs font-medium" :class="statusColors[selectedOrder.status] || 'bg-slate-100 text-slate-500'">
                {{ statusLabels[selectedOrder.status] || selectedOrder.status }}
              </span>
            </div>

            <!-- 快递信息 -->
            <div v-if="selectedOrder.express_company" class="bg-slate-50 rounded-lg p-3 space-y-1">
              <p class="text-xs text-slate-500">{{ selectedOrder.express_company }}</p>
              <p class="text-xs font-medium text-slate-700">单号: {{ selectedOrder.tracking_number }}</p>
            </div>

            <!-- 物流轨迹 -->
            <div>
              <h3 class="text-xs font-semibold text-slate-600 mb-3">物流轨迹</h3>
              <div class="relative">
                <!-- 时间线竖线 -->
                <div class="absolute left-[11px] top-2 bottom-2 w-0.5 bg-slate-200"></div>

                <div v-if="selectedOrder.logistics.length === 0" class="text-xs text-slate-400 pl-8">
                  暂无物流信息
                </div>

                <div
                  v-for="(evt, i) in selectedOrder.logistics" :key="i"
                  class="relative flex items-start gap-3 pb-4 last:pb-0"
                >
                  <div class="relative z-10 w-6 h-6 rounded-full bg-white border-2 border-slate-200 flex items-center justify-center shrink-0"
                    :class="{ 'border-accent bg-accent-soft': i === selectedOrder.logistics.length - 1 }">
                    <span class="text-xs">{{ eventIcons[evt.event_type] || '📋' }}</span>
                  </div>
                  <div class="flex-1 min-w-0 pt-0.5">
                    <p class="text-xs text-slate-700 leading-relaxed">{{ evt.message }}</p>
                    <p v-if="evt.location" class="text-[10px] text-slate-400 mt-0.5">{{ evt.location }}</p>
                    <p class="text-[10px] text-slate-400 mt-0.5">{{ evt.timestamp?.slice(0, 19)?.replace('T', ' ') }}</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- 错误信息 -->
            <p v-if="errorMsg" class="text-xs text-red-500">{{ errorMsg }}</p>
          </div>

          <!-- 底部按钮 -->
          <div class="flex items-center justify-between px-5 py-3 border-t border-slate-100 shrink-0">
            <button
              @click="handleDelete(selectedOrder.order_id)"
              :disabled="detailLoading"
              class="px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100 disabled:opacity-40 transition-colors"
            >🗑 删除</button>
            <div class="flex gap-2">
              <span class="text-[10px] text-slate-400">⚠️ 模拟数据</span>
              <button
                @click="handleAdvance(selectedOrder.order_id)"
                :disabled="detailLoading || selectedOrder.status === 'delivered' || selectedOrder.status === 'refunded'"
                class="px-3 py-1.5 text-xs font-medium text-white bg-accent rounded-lg hover:bg-accent/90 disabled:opacity-40 transition-colors"
              >
                {{ detailLoading ? '处理中…' : '推进物流' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
