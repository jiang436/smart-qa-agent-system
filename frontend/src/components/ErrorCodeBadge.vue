<script setup lang="ts">
defineProps<{
  code: string
  cause?: string
}>()

const colors: Record<string, string> = {
  E01: 'bg-amber-50 text-amber-700 border-amber-200',
  E02: 'bg-orange-50 text-orange-700 border-orange-200',
  E03: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  E04: 'bg-blue-50 text-blue-700 border-blue-200',
  E05: 'bg-danger/5 text-danger border-danger/20',
  E06: 'bg-purple-50 text-purple-700 border-purple-200',
  E07: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  E08: 'bg-slate-50 text-slate-600 border-slate-200',
}
</script>

<template>
  <div :class="['inline-flex items-center gap-1.5 px-2.5 py-1 rounded border font-mono text-xs font-semibold', (colors as any)[code] || colors.E08]">
    {{ code }}
    <span v-if="cause" class="font-sans font-normal text-[10px] opacity-70">{{ cause }}</span>
  </div>
</template>
