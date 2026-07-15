<script setup lang="ts">
defineProps<{ message: string }>()
defineEmits<{ dismiss: [] }>()
</script>

<template>
  <div class="flex items-start gap-3 p-4 bg-danger-soft border border-red-200 rounded-xl animate-slide-up">
    <svg class="w-4 h-4 text-danger shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
      <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
    </svg>
    <div class="flex-1 text-sm text-red-700 leading-relaxed">{{ message }}</div>
    <button
      @click="$emit('dismiss')"
      class="text-red-400 hover:text-red-600 transition-base shrink-0"
      title="关闭"
    >
      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  </div>
</template>
