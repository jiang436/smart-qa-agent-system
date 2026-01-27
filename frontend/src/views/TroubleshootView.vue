<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAppStore } from '@/stores/app'
import { useSSE } from '@/composables/useSSE'
import ErrorCodeBadge from '@/components/ErrorCodeBadge.vue'

const chat = useChatStore()
const app = useAppStore()
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

  // Check for error code
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
    <!-- Header -->
    <header class="flex items-center justify-between px-5 py-3 bg-white border-b border-slate-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-slate-800">故障排查</h1>
        <p class="text-[11px] text-slate-400">引导式诊断 · 错误码速查</p>
      </div>
      <button @click="onStartDiagnosis" class="text-[11px] px-2.5 py-1 rounded bg-accent text-white hover:bg-accent/90 transition-colors">
        开始排查
      </button>
    </header>

    <div class="flex-1 overflow-hidden flex">
      <!-- Left: Diagnosis flow -->
      <div class="flex-1 flex flex-col">
        <!-- Progress -->
        <div v-if="step > 0" class="px-5 py-2 bg-accent-soft/50 border-b border-accent-soft">
          <div class="flex items-center gap-2 text-xs text-accent font-medium">
            <span>排查进度</span>
            <div class="flex-1 h-1 bg-accent-soft rounded-full">
              <div class="h-full bg-accent rounded-full transition-all" :style="{ width: `${(step / diagnosisSteps.length) * 100}%` }" />
            </div>
            <span>{{ step }}/{{ diagnosisSteps.length }}</span>
          </div>
        </div>

        <!-- Chat area -->
        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          <div v-if="chat.messages.length === 0 && step === 0" class="flex flex-col items-center justify-center h-full text-center">
            <div class="text-5xl mb-4">🔧</div>
            <h2 class="text-lg font-semibold text-slate-700 mb-1">故障排查助手</h2>
            <p class="text-sm text-slate-400 mb-4">点击"开始排查"启动引导式诊断，或直接输入错误码快速查询。</p>
          </div>

          <div v-for="msg in chat.messages" :key="msg.id"
            :class="msg.role === 'user' ? 'text-right' : 'text-left'"
          >
            <div :class="[
              'inline-block max-w-[80%] rounded-lg px-3 py-2 text-sm',
              msg.role === 'user' ? 'bg-accent text-white' : 'bg-white border border-slate-200'
            ]">
              {{ msg.content }}
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="px-5 py-3 bg-white border-t border-slate-200">
          <div class="flex gap-2">
            <input
              v-model="userAnswer"
              @keydown.enter="onAnswer"
              placeholder="输入你的回答或错误码…"
              class="flex-1 rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:border-accent"
            />
            <button
              @click="onAnswer"
              class="px-4 py-2 rounded-md bg-accent text-white text-sm hover:bg-accent/90 transition-colors"
            >发送</button>
          </div>
        </div>
      </div>

      <!-- Right: Error codes cheatsheet -->
      <aside class="w-56 bg-bg-secondary border-l border-slate-200 overflow-y-auto p-4 shrink-0">
        <h3 class="text-xs font-semibold text-slate-500 uppercase mb-3">错误码速查</h3>
        <div class="space-y-2">
          <div
            v-for="ec in errorCodes"
            :key="ec.code"
            @click="userAnswer = ec.code; onAnswer()"
            class="cursor-pointer hover:opacity-80 transition-opacity"
          >
            <ErrorCodeBadge :code="ec.code" :cause="ec.cause" />
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
