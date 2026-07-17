<script setup lang="ts">
import type { Message } from '@/stores/chat'
import CitationCard from './CitationCard.vue'
import { computed } from 'vue'

const props = defineProps<{ msg: Message }>()

const isUser = computed(() => props.msg.role === 'user')
</script>

<template>
  <div :class="['flex animate-slide-up', isUser ? 'justify-end' : 'justify-start']">
    <div
      :class="[
        'max-w-[75%] message-prose',
        isUser
          ? 'bg-accent text-white rounded-2xl rounded-br-md px-4 py-2.5 shadow-e1'
          : 'glass-card rounded-2xl rounded-bl-md px-5 py-3 shadow-e1'
      ]"
    >
      <!-- Content -->
      <div
        v-if="msg.isStreaming"
        class="typing-cursor whitespace-pre-wrap break-words text-sm leading-relaxed"
      >{{ msg.content }}</div>
      <div v-else class="whitespace-pre-wrap break-words text-sm leading-relaxed">{{ msg.content }}</div>

      <!-- Citations -->
      <div v-if="msg.citations?.length && !isUser" class="mt-3 space-y-2">
        <CitationCard
          v-for="cite in msg.citations"
          :key="cite.doc_id"
          :text="cite.matched_sentence"
          :source="cite.source"
        />
      </div>
    </div>
  </div>
</template>
