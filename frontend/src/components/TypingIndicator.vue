<template>
  <div class="flex items-center gap-1.5 py-2">
    <span class="w-1.5 h-1.5 rounded-full bg-slate-300 typing-dot-first" />
    <span class="w-1.5 h-1.5 rounded-full bg-slate-400 typing-dot-second" />
    <span class="w-1.5 h-1.5 rounded-full bg-slate-500 typing-dot-third" />
  </div>
</template>

<style scoped>
.typing-dot-first  { animation: typing-dot 1.4s infinite both; animation-delay: 0s; }
.typing-dot-second { animation: typing-dot 1.4s infinite both; animation-delay: 0.2s; }
.typing-dot-third  { animation: typing-dot 1.4s infinite both; animation-delay: 0.4s; }
@keyframes typing-dot {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.3; }
  30% { transform: translateY(-6px); opacity: 1; }
}
</style>
