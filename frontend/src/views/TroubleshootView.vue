<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSSE } from '@/composables/useSSE'
import ErrorCodeBadge from '@/components/ErrorCodeBadge.vue'

const chat = useChatStore()
const { send } = useSSE()

const step = ref(0)
const symptoms = ref('')
const userAnswer = ref('')

const errorCodes = [
  { code: 'E01', cause: '跌落传感器异常' },
  { code: 'E02', cause: '驱动轮卡住' },
  { code: 'E03', cause: '边刷不转' },
  { code: 'E04', cause: '尘盒未安装' },
  { code: 'E05', cause: '电池过热' },
  { code: 'E06', cause: '激光雷达异常' },
  { code: 'E07', cause: 'Wi-Fi 连接失败' },
  { code: 'E08', cause: '水箱未安装' },
]

const diagnosisSteps = [
  { question: '设备是否有错误码显示？如果有，请直接输入错误码。', key: 'error_code' },
  { question: '设备是否能正常开机？电源指示灯是否亮？', key: 'power' },
  { question: '最后一次正常使用是什么时候？', key: 'last_use' },
  { question: '是否尝试过重启设备？（长按开机键10秒）', key: 'restart' },
]

const currentStep = computed(() => diagnosisSteps[step.value])

function onStartDiagnosis() {
  step.value = 0
  symptoms.value = ''
  chat.clearMessages()
  chat.addMessage({ role: 'assistant', content: '开始故障排查。请描述您遇到的问题：' })
}

function onAnswer() {
  if (!userAnswer.value.trim()) return
  const answer = userAnswer.value.trim()
  userAnswer.value = ''

  const codeMatch = answer.match(/[eE](\d{2,3})/)
  if (codeMatch) {
    const code = `E${codeMatch[1]}`
    send(`错误码${code}`)
    step.value = diagnosisSteps.length
    return
  }

  if (step.value < diagnosisSteps.length) {
    chat.addMessage({ role: 'user', content: answer })
    chat.addMessage({ role: 'assistant', content: currentStep.value.question })
    step.value++
  } else {
    send(symptoms.value || answer)
  }
}
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center justify-between px-6 py-3 bg-surface border-b border-neutral-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-neutral-800">故障排查</h1>
        <p class="text-[11px] text-neutral-400 mt-0.5">引导式诊断 - 错误码速查</p>
      </div>
      <button
        @click="onStartDiagnosis"
        class="px-3 py-1.5 text-xs font-medium rounded-lg bg-accent text-white hover:bg-accent-hover transition-base"
      >开始排查</button>
    </header>

    <div class="flex-1 overflow-hidden flex">
      <!-- Diagnosis flow -->
      <div class="flex-1 flex flex-col">
        <div v-if="step > 0" class="px-6 py-2 bg-accent-soft/60 border-b border-accent-muted/30">
          <div class="flex items-center gap-2.5 text-xs text-accent font-medium">
            <span>排查进度</span>
            <div class="flex-1 h-1.5 bg-accent-muted/40 rounded-full overflow-hidden">
              <div class="h-full bg-accent rounded-full transition-base" :style="{ width: `${(step / diagnosisSteps.length) * 100}%` }" />
            </div>
            <span class="font-mono">{{ step }}/{{ diagnosisSteps.length }}</span>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          <div v-if="chat.messages.length === 0 && step === 0" class="flex flex-col items-center justify-center min-h-full text-center">
            <div class="w-16 h-16 rounded-2xl bg-accent-soft flex items-center justify-center mb-6">
              <svg class="w-8 h-8 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17l-4.25 4.25a2.25 2.25 0 01-3.182-3.182l4.25-4.25m7.061-7.06l-2.97 2.97m0 0l-2.97 2.97m2.97-2.97a4.5 4.5 0 00-6.364 0l-6 6a4.5 4.5 0 006.364 6.364l6-6a4.5 4.5 0 000-6.364z" />
              </svg>
            </div>
            <h2 class="text-lg font-semibold text-neutral-800 mb-2">故障排查助手</h2>
            <p class="text-sm text-neutral-400 max-w-prose mb-4">点击"开始排查"启动引导式诊断，或直接输入错误码快速查询。</p>
          </div>

          <div v-for="msg in chat.messages" :key="msg.id"
            :class="msg.role === 'user' ? 'text-right' : 'text-left'"
          >
            <div :class="[
              'inline-block max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
              msg.role === 'user'
                ? 'bg-accent text-white rounded-br-md'
                : 'glass-card rounded-bl-md'
            ]">
              {{ msg.content }}
            </div>
          </div>
        </div>

        <div class="px-6 py-4 bg-surface border-t border-neutral-200">
          <div class="flex gap-2.5 max-w-2xl">
            <input
              v-model="userAnswer"
              @keydown.enter="onAnswer"
              placeholder="输入回答或错误码..."
              class="flex-1 rounded-lg border border-neutral-200 bg-bg-primary px-4 py-2.5 text-sm placeholder:text-neutral-400 focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft transition-base"
            />
            <button
              @click="onAnswer"
              class="px-5 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover transition-base"
            >发送</button>
          </div>
        </div>
      </div>

      <!-- Error code cheatsheet -->
      <aside class="w-56 bg-bg-secondary border-l border-neutral-200 overflow-y-auto p-4 shrink-0">
        <h3 class="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-3">错误码速查</h3>
        <div class="space-y-2">
          <div
            v-for="ec in errorCodes"
            :key="ec.code"
            @click="userAnswer = ec.code; onAnswer()"
            class="cursor-pointer hover:opacity-80 transition-base"
          >
            <ErrorCodeBadge :code="ec.code" :cause="ec.cause" />
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
