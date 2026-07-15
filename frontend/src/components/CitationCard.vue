<script setup lang="ts">
defineProps<{ text: string; source?: string }>()
</script>

<template>
  <div class="p-3 bg-accent-soft/40 rounded-lg border border-accent-muted/30 text-xs leading-relaxed">
    <div class="flex items-center gap-1.5 text-accent font-medium mb-1.5">
      <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
      </svg>
      知识引用
    </div>
    <p class="text-neutral-600">{{ text }}</p>
    <p v-if="source" class="text-[10px] text-neutral-400 mt-1.5">来源: {{ source }}</p>
  </div>
</template>
