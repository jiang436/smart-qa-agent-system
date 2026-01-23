<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'

const app = useAppStore()

const statusColor = computed(() => app.deviceOnline ? 'bg-success' : 'bg-slate-400')
const statusLabel = computed(() => app.deviceOnline ? '在线' : '离线')
</script>

<template>
  <div class="flex items-center gap-2">
    <div class="pulse-ring-container">
      <div :class="statusColor" class="w-2.5 h-2.5 rounded-full relative z-10" />
      <div v-if="app.deviceOnline" class="pulse-ring" />
    </div>
    <span class="text-xs font-medium text-slate-500">{{ app.deviceModel }}</span>
    <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">{{ statusLabel }}</span>
  </div>
</template>
