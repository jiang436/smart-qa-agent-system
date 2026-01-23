<script setup lang="ts">
defineProps<{ intent: string }>()

const labels: Record<string, string> = {
  qa: '知识问答',
  troubleshoot: '故障排查',
  consumables: '耗材管理',
  general: '综合',
}

const colors: Record<string, string> = {
  qa: 'bg-accent-soft text-accent',
  troubleshoot: 'bg-amber-50 text-amber-700',
  consumables: 'bg-emerald-50 text-emerald-700',
  general: 'bg-slate-100 text-slate-600',
}
</script>

<template>
  <span :class="['inline-block text-[10px] font-medium px-1.5 py-0.5 rounded', (colors as any)[intent] || colors.general]">
    {{ (labels as any)[intent] || intent }}
  </span>
</template>
