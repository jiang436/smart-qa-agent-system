<script setup lang="ts">
import { ref } from 'vue'

const period = ref<'monthly' | 'weekly'>('monthly')
const loading = ref(false)

const mockStats = {
  total_cleans: 28,
  total_area: 1240.5,
  total_duration: 1024,
  avg_area_per_clean: 44.3,
  error_count: 3,
}

const consumables = [
  { name: '边刷', remaining: 45, total: 120, status: 'good' },
  { name: '主刷', remaining: 120, total: 180, status: 'good' },
  { name: 'HEPA滤网', remaining: 12, total: 90, status: 'warning' },
  { name: '拖布', remaining: 8, total: 60, status: 'danger' },
]

const statusColors: Record<string, string> = {
  good: 'bg-success',
  warning: 'bg-amber-400',
  danger: 'bg-danger',
}

const statusLabels: Record<string, string> = {
  good: '正常',
  warning: '即将到期',
  danger: '建议更换',
}
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center justify-between px-5 py-3 bg-white border-b border-slate-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-slate-800">使用报告</h1>
        <p class="text-[11px] text-slate-400">X30 Pro · 最近30天</p>
      </div>
      <div class="flex gap-1 bg-bg-secondary rounded-md p-0.5">
        <button
          v-for="p in [{ key: 'weekly', label: '周报' }, { key: 'monthly', label: '月报' }]"
          :key="p.key"
          @click="period = p.key as any"
          :class="[
            'px-3 py-1 text-xs rounded transition-colors',
            period === p.key ? 'bg-white text-accent shadow-e1' : 'text-slate-500'
          ]"
        >{{ p.label }}</button>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-5 space-y-5">
      <!-- Stats -->
      <div class="grid grid-cols-4 gap-3">
        <div class="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <div class="text-2xl font-bold text-slate-800">{{ mockStats.total_cleans }}</div>
          <div class="text-[11px] text-slate-400 mt-1">清扫次数</div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <div class="text-2xl font-bold text-slate-800">{{ mockStats.total_area }}<span class="text-sm font-normal text-slate-400">m²</span></div>
          <div class="text-[11px] text-slate-400 mt-1">清扫面积</div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <div class="text-2xl font-bold text-slate-800">{{ mockStats.total_duration }}<span class="text-sm font-normal text-slate-400">min</span></div>
          <div class="text-[11px] text-slate-400 mt-1">累计时长</div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <div class="text-2xl font-bold text-slate-800">{{ mockStats.error_count }}<span class="text-sm font-normal text-slate-400">次</span></div>
          <div class="text-[11px] text-slate-400 mt-1">异常事件</div>
        </div>
      </div>

      <!-- Consumable status -->
      <div class="bg-white rounded-lg border border-slate-200 p-5">
        <h3 class="text-sm font-semibold text-slate-800 mb-4">耗材状态</h3>
        <div class="space-y-3">
          <div v-for="c in consumables" :key="c.name" class="flex items-center gap-3">
            <span class="text-xs text-slate-600 w-16 shrink-0">{{ c.name }}</span>
            <div class="flex-1 h-2 bg-slate-100 rounded-full">
              <div
                :class="statusColors[c.status]"
                class="h-full rounded-full transition-all"
                :style="{ width: `${(c.remaining / c.total) * 100}%` }"
              />
            </div>
            <span class="text-[11px] text-slate-400 w-16 text-right">{{ c.remaining }}/{{ c.total }}天</span>
            <span
              :class="[
                'text-[10px] px-1.5 py-0.5 rounded-full',
                c.status === 'good' ? 'bg-emerald-50 text-emerald-600' :
                c.status === 'warning' ? 'bg-amber-50 text-amber-600' :
                'bg-red-50 text-red-600'
              ]"
            >{{ statusLabels[c.status] }}</span>
          </div>
        </div>
      </div>

      <!-- Recommendations -->
      <div class="bg-white rounded-lg border border-slate-200 p-5">
        <h3 class="text-sm font-semibold text-slate-800 mb-3">优化建议</h3>
        <ul class="space-y-2 text-sm text-slate-600">
          <li class="flex items-start gap-2">
            <span class="text-accent mt-0.5">•</span>
            您的平均清扫面积 44.3m²，适合当前使用频率，建议保持每天清扫的习惯
          </li>
          <li class="flex items-start gap-2">
            <span class="text-amber-500 mt-0.5">•</span>
            HEPA滤网和拖布即将到期，建议提前购买备件
          </li>
          <li class="flex items-start gap-2">
            <span class="text-accent mt-0.5">•</span>
            出现过 3 次异常事件，建议检查设备轮子和边刷是否有缠绕物
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
