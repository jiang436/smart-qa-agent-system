<script setup lang="ts">
import type { Message } from '@/stores/chat'
import IntentBadge from './IntentBadge.vue'

defineProps<{ msg: Message }>()
</script>

<template>
  <div :class="msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'">
    <div
      :class="[
        'max-w-[75%] rounded-lg px-4 py-2.5 text-sm leading-relaxed',
        msg.role === 'user'
          ? 'bg-accent text-white rounded-br-sm'
          : 'bg-white border border-slate-200 rounded-bl-sm shadow-e1'
      ]"
    >
      <IntentBadge v-if="msg.intent && msg.role === 'assistant'" :intent="msg.intent" class="mb-1.5" />
      <div v-if="msg.isStreaming" class="typing-cursor whitespace-pre-wrap break-words">{{ msg.content }}</div>
      <div v-else class="whitespace-pre-wrap break-words">{{ msg.content }}</div>
    </div>
  </div>
</template>
