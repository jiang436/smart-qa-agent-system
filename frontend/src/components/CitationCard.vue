<script setup lang="ts">
defineProps<{
  text: string
  source?: string
}>()
</script>

<template>
  <div class="mt-2 p-2.5 bg-accent-soft/50 rounded-md border border-accent-soft text-xs">
    <div class="flex items-center gap-1 text-accent font-medium mb-1">
      <span class="i-lucide-book-open w-3 h-3" /> 知识引用
    </div>
    <p class="text-slate-600 leading-relaxed">{{ text }}</p>
    <p v-if="source" class="text-[10px] text-slate-400 mt-1">来源: {{ source }}</p>
  </div>
</template>
