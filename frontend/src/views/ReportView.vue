<script setup lang="ts">
import { ref } from 'vue'

const period = ref<'monthly' | 'weekly'>('monthly')

const stats = {
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

const statusConfig: Record<string, { bar: string; badge: string; label: string }> = {
  good: { bar: 'bg-emerald-400', badge: 'bg-emerald-50 text-emerald-600', label: '正常' },
  warning: { bar: 'bg-amber-400', badge: 'bg-amber-50 text-amber-600', label: '即将到期' },
  danger: { bar: 'bg-red-400', badge: 'bg-red-50 text-red-600', label: '建议更换' },
}
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center justify-between px-6 py-3 bg-surface border-b border-neutral-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-neutral-800">使用报告</h1>
        <p class="text-[11px] text-neutral-400 mt-0.5">X30 Pro - 最近30天</p>
      </div>
      <div class="flex gap-0.5 bg-bg-secondary rounded-lg p-0.5">
        <button
          v-for="p in [{ key: 'weekly', label: '周报' }, { key: 'monthly', label: '月报' }]"
          :key="p.key"
          @click="period = p.key as any"
          :class="[
            'px-3.5 py-1.5 text-xs font-medium rounded-md transition-base',
            period === p.key ? 'bg-surface text-accent shadow-e1' : 'text-neutral-500 hover:text-neutral-700'
          ]"
        >{{ p.label }}</button>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-6 space-y-5">
      <div class="grid grid-cols-4 gap-3">
        <div v-for="stat in [
          { val: stats.total_cleans, unit: '', label: '清扫次数' },
          { val: stats.total_area, unit: 'm²', label: '清扫面积' },
          { val: stats.total_duration, unit: 'min', label: '累计时长' },
          { val: stats.error_count, unit: '次', label: '异常事件' },
        ]" :key="stat.label" class="bg-surface border border-neutral-200 rounded-xl p-5 text-center">
          <div class="text-2xl font-bold text-neutral-800">
            {{ stat.val }}<span class="text-sm font-normal text-neutral-400 ml-1">{{ stat.unit }}</span>
          </div>
          <div class="text-[11px] text-neutral-400 mt-1.5">{{ stat.label }}</div>
        </div>
      </div>

      <div class="bg-surface border border-neutral-200 rounded-xl p-6">
        <h3 class="text-sm font-semibold text-neutral-800 mb-5">耗材状态</h3>
        <div class="space-y-4">
          <div v-for="c in consumables" :key="c.name" class="flex items-center gap-4">
            <span class="text-xs text-neutral-600 w-20 shrink-0">{{ c.name }}</span>
            <div class="flex-1 h-2 bg-neutral-100 rounded-full overflow-hidden">
              <div
                :class="statusConfig[c.status].bar"
                class="h-full rounded-full transition-base"
                :style="{ width: `${(c.remaining / c.total) * 100}%` }"
              />
            </div>
            <span class="text-[11px] text-neutral-400 w-20 text-right font-mono">{{ c.remaining }}/{{ c.total }}天</span>
            <span :class="statusConfig[c.status].badge" class="text-[10px] px-1.5 py-0.5 rounded-md font-medium">{{ statusConfig[c.status].label }}</span>
          </div>
        </div>
      </div>

      <div class="bg-surface border border-neutral-200 rounded-xl p-6">
        <h3 class="text-sm font-semibold text-neutral-800 mb-4">优化建议</h3>
        <ul class="space-y-2.5 text-sm text-neutral-600 leading-relaxed">
          <li class="flex items-start gap-2.5">
            <span class="w-1.5 h-1.5 rounded-full bg-accent mt-2 shrink-0" />
            平均清扫面积 44.3m²，适合当前使用频率，建议保持每天清扫。
          </li>
          <li class="flex items-start gap-2.5">
            <span class="w-1.5 h-1.5 rounded-full bg-amber-400 mt-2 shrink-0" />
            HEPA滤网和拖布即将到期，建议提前购买备件。
          </li>
          <li class="flex items-start gap-2.5">
            <span class="w-1.5 h-1.5 rounded-full bg-accent mt-2 shrink-0" />
            出现过 3 次异常事件，建议检查设备轮子和边刷是否有缠绕物。
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
