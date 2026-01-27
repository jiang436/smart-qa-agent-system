<script setup lang="ts">
import { ref } from 'vue'

const metrics = ref({
  totalRequests: 12580,
  avgLatency: 1.8,
  cacheHitRate: 72.5,
  activeSessions: 12,
  errorRate: 1.2,
})

const intentDistribution = [
  { intent: 'qa', label: '知识问答', count: 6420, color: 'bg-accent' },
  { intent: 'troubleshoot', label: '故障排查', count: 3850, color: 'bg-amber-400' },
  { intent: 'consumables', label: '耗材管理', count: 1480, color: 'bg-emerald-400' },
  { intent: 'general', label: '其他', count: 830, color: 'bg-slate-400' },
]

const maxCount = Math.max(...intentDistribution.map(i => i.count))

const recentSessions = [
  { id: 'sess_01', user: 'U1001', intent: 'qa', messages: 6, time: '2分钟前' },
  { id: 'sess_02', user: 'U1002', intent: 'troubleshoot', messages: 12, time: '15分钟前' },
  { id: 'sess_03', user: 'U1003', intent: 'consumables', messages: 8, time: '32分钟前' },
  { id: 'sess_04', user: 'U1001', intent: 'qa', messages: 4, time: '1小时前' },
  { id: 'sess_05', user: 'U1002', intent: 'qa', messages: 3, time: '2小时前' },
]

const intentLabels: Record<string, string> = {
  qa: '知识问答', troubleshoot: '故障排查', consumables: '耗材管理', general: '综合'
}
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center justify-between px-5 py-3 bg-white border-b border-slate-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-slate-800">管理后台</h1>
        <p class="text-[11px] text-slate-400">系统运行状态 · 实时数据</p>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-5 space-y-5">
      <!-- Key metrics -->
      <div class="grid grid-cols-5 gap-3">
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">总请求数</div>
          <div class="text-xl font-bold text-slate-800 mt-1">{{ metrics.totalRequests.toLocaleString() }}</div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">平均延迟</div>
          <div class="text-xl font-bold text-slate-800 mt-1">{{ metrics.avgLatency }}<span class="text-sm font-normal text-slate-400">s</span></div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">缓存命中率</div>
          <div class="text-xl font-bold text-success mt-1">{{ metrics.cacheHitRate }}<span class="text-sm font-normal text-slate-400">%</span></div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">活跃会话</div>
          <div class="text-xl font-bold text-slate-800 mt-1">{{ metrics.activeSessions }}</div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">错误率</div>
          <div class="text-xl font-bold text-amber-500 mt-1">{{ metrics.errorRate }}<span class="text-sm font-normal text-slate-400">%</span></div>
        </div>
      </div>

      <!-- Intent distribution -->
      <div class="bg-white rounded-lg border border-slate-200 p-5">
        <h3 class="text-xs font-semibold text-slate-500 uppercase mb-4">意图分布</h3>
        <div class="space-y-2">
          <div v-for="item in intentDistribution" :key="item.intent" class="flex items-center gap-3">
            <span class="text-xs text-slate-600 w-16">{{ item.label }}</span>
            <div class="flex-1 h-5 bg-slate-50 rounded-full overflow-hidden">
              <div
                :class="item.color"
                class="h-full rounded-full flex items-center justify-end pr-2 transition-all"
                :style="{ width: `${(item.count / maxCount) * 100}%` }"
              >
                <span class="text-[10px] text-white font-medium">{{ item.count.toLocaleString() }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent sessions -->
      <div class="bg-white rounded-lg border border-slate-200">
        <div class="px-5 py-3 border-b border-slate-100">
          <h3 class="text-xs font-semibold text-slate-500 uppercase">最近会话</h3>
        </div>
        <table class="w-full text-xs">
          <thead>
            <tr class="text-slate-400 border-b border-slate-100">
              <th class="text-left px-5 py-2 font-medium">会话 ID</th>
              <th class="text-left px-5 py-2 font-medium">用户</th>
              <th class="text-left px-5 py-2 font-medium">意图</th>
              <th class="text-left px-5 py-2 font-medium">消息数</th>
              <th class="text-left px-5 py-2 font-medium">时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in recentSessions" :key="s.id" class="border-b border-slate-50 hover:bg-slate-50">
              <td class="px-5 py-2.5 font-mono text-slate-500">{{ s.id }}</td>
              <td class="px-5 py-2.5">{{ s.user }}</td>
              <td class="px-5 py-2.5">
                <span :class="[
                  'px-1.5 py-0.5 rounded text-[10px] font-medium',
                  s.intent === 'qa' ? 'bg-accent-soft text-accent' :
                  s.intent === 'troubleshoot' ? 'bg-amber-50 text-amber-700' :
                  s.intent === 'consumables' ? 'bg-emerald-50 text-emerald-700' :
                  'bg-slate-100 text-slate-600'
                ]">{{ intentLabels[s.intent] || s.intent }}</span>
              </td>
              <td class="px-5 py-2.5 text-slate-500">{{ s.messages }}</td>
              <td class="px-5 py-2.5 text-slate-400">{{ s.time }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
