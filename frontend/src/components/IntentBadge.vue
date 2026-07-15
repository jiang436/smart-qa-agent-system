<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ intent: string }>()

const config = computed(() => {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    qa: { label: '知识问答', color: 'text-accent', bg: 'bg-accent-soft' },
    troubleshoot: { label: '故障排查', color: 'text-amber-700', bg: 'bg-amber-50' },
    consumables: { label: '耗材管理', color: 'text-emerald-700', bg: 'bg-emerald-50' },
    device_control: { label: '设备控制', color: 'text-sky-700', bg: 'bg-sky-50' },
    report: { label: '使用报告', color: 'text-violet-700', bg: 'bg-violet-50' },
    sql_query: { label: '数据查询', color: 'text-slate-700', bg: 'bg-slate-100' },
    general: { label: '综合', color: 'text-neutral-600', bg: 'bg-neutral-100' },
  }
  return map[props.intent] || map.general
})
</script>

<template>
  <span :class="[config.color, config.bg]" class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium">
    {{ config.label }}
  </span>
</template>
