<script setup lang="ts">
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
</script>

<template>
  <div class="flex items-center gap-1.5">
    <span
      :class="[
        'w-2 h-2 rounded-full transition-base',
        chat.isProcessing ? 'bg-accent animate-pulse' : 'bg-emerald-400'
      ]"
    />
    <span class="text-[11px] text-neutral-400 font-medium">
      {{ chat.isProcessing ? '处理中' : '在线' }}
    </span>
  </div>
</template>
