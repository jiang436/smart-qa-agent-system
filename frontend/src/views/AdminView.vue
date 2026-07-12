<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getKnowledgeStatus, uploadKnowledgeFile, reloadKnowledge, type KnowledgeStatus } from '@/api'

const metrics = ref({
  totalRequests: 12580,
  avgLatency: 1.8,
  cacheHitRate: 72.5,
  activeSessions: 12,
  errorRate: 1.2,
})

const intentDistribution = [
  { intent: 'qa', label: '知识问答', count: 6420, color: 'bg-accent' },
  { intent: 'troubleshoot', label: '故障排查', count: 3850, color: 'bg-amber-400' },
  { intent: 'consumables', label: '耗材管理', count: 1480, color: 'bg-emerald-400' },
  { intent: 'general', label: '其他', count: 830, color: 'bg-slate-400' },
]
const maxCount = Math.max(...intentDistribution.map(i => i.count))

const recentSessions = [
  { id: 'sess_01', user: 'U1001', intent: 'qa', messages: 6, time: '2分钟前' },
  { id: 'sess_02', user: 'U1002', intent: 'troubleshoot', messages: 12, time: '15分钟前' },
  { id: 'sess_03', user: 'U1003', intent: 'consumables', messages: 8, time: '32分钟前' },
  { id: 'sess_04', user: 'U1001', intent: 'qa', messages: 4, time: '1小时前' },
  { id: 'sess_05', user: 'U1002', intent: 'qa', messages: 3, time: '2小时前' },
]
const intentLabels: Record<string, string> = {
  qa: '知识问答', troubleshoot: '故障排查', consumables: '耗材管理', general: '综合'
}

// ── Knowledge ──
const kb = ref<KnowledgeStatus | null>(null)
const uploadFile = ref<File | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadResult = ref('')
const reloading = ref(false)
const reloadResult = ref('')
const kbLoading = ref(false)
const dragging = ref(false)

async function loadStatus() {
  kbLoading.value = true
  try {
    kb.value = await getKnowledgeStatus()
  } catch { /* ignore */ }
  kbLoading.value = false
}

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    uploadFile.value = input.files[0]
    uploadResult.value = ''
  }
}

async function doUpload() {
  if (!uploadFile.value) return
  uploading.value = true
  uploadProgress.value = 0
  uploadResult.value = ''
  try {
    const res = await uploadKnowledgeFile(uploadFile.value, (pct) => { uploadProgress.value = pct })
    uploadResult.value = `✅ 上传成功: ${res.chunks} 个片段，维度 ${res.dimension}`
    uploadFile.value = null
    loadStatus()
  } catch (e: any) {
    uploadResult.value = `❌ ${e.message || '上传失败'}`
  }
  uploading.value = false
}

async function doReload() {
  if (!confirm('确认重新加载全部知识库？现有索引将被删除并重建。')) return
  reloading.value = true
  reloadResult.value = ''
  try {
    const res = await reloadKnowledge()
    reloadResult.value = `✅ ${res.message || '重新加载完成'}`
    loadStatus()
  } catch (e: any) {
    reloadResult.value = `❌ ${e.message || '重新加载失败'}`
  }
  reloading.value = false
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  dragging.value = true
}
function onDragLeave() { dragging.value = false }
async function onDrop(e: DragEvent) {
  e.preventDefault()
  dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && (file.name.endsWith('.pdf') || file.name.endsWith('.md') || file.name.endsWith('.txt'))) {
    uploadFile.value = file
    uploadResult.value = ''
  }
}

onMounted(loadStatus)
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center justify-between px-5 py-3 bg-white border-b border-slate-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-slate-800">管理后台</h1>
        <p class="text-[11px] text-slate-400">系统运行状态 · 知识库管理</p>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-5 space-y-5">
      <!-- Key metrics -->
      <div class="grid grid-cols-5 gap-3">
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">总请求数</div>
          <div class="text-xl font-bold text-slate-800 mt-1">{{ metrics.totalRequests.toLocaleString() }}</div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">平均延迟</div>
          <div class="text-xl font-bold text-slate-800 mt-1">{{ metrics.avgLatency }}<span class="text-sm font-normal text-slate-400">s</span></div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">缓存命中率</div>
          <div class="text-xl font-bold text-success mt-1">{{ metrics.cacheHitRate }}<span class="text-sm font-normal text-slate-400">%</span></div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">活跃会话</div>
          <div class="text-xl font-bold text-slate-800 mt-1">{{ metrics.activeSessions }}</div>
        </div>
        <div class="bg-white rounded-lg border border-slate-200 p-4">
          <div class="text-[11px] text-slate-400">错误率</div>
          <div class="text-xl font-bold text-amber-500 mt-1">{{ metrics.errorRate }}<span class="text-sm font-normal text-slate-400">%</span></div>
        </div>
      </div>

      <!-- Knowledge Base -->
      <div class="bg-white rounded-lg border border-slate-200 p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-xs font-semibold text-slate-500 uppercase">知识库管理</h3>
          <div class="flex items-center gap-2">
            <button @click="loadStatus" class="text-[11px] text-accent hover:underline">刷新</button>
          </div>
        </div>

        <!-- Status -->
        <div class="flex items-center gap-4 mb-4 text-xs text-slate-600">
          <div v-if="kbLoading">加载中…</div>
          <template v-else-if="kb">
            <span>向量库: <code class="text-slate-800 font-mono">{{ kb.collection || '-' }}</code></span>
            <span>文档数: <strong>{{ kb.total_documents ?? '?' }}</strong></span>
            <span>向量维度: <strong>{{ kb.dimension ?? '?' }}</strong></span>
            <span v-if="kb.status === 'empty'" class="text-amber-500">（知识库为空）</span>
            <span v-else-if="kb.status === 'error'" class="text-red-500">{{ kb.message }}</span>
          </template>
          <div v-else class="text-slate-400">无法获取知识库状态</div>
        </div>

        <!-- Upload -->
        <div
          @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop"
          :class="['border-2 border-dashed rounded-lg p-5 text-center transition-colors cursor-pointer',
            dragging ? 'border-accent bg-accent-soft' : 'border-slate-200 hover:border-slate-300']"
          @click="$refs.fileInput?.click()"
        >
          <input ref="fileInput" type="file" accept=".pdf,.md,.txt" class="hidden" @change="onFileSelected" />
          <div v-if="!uploadFile" class="text-xs text-slate-400">
            <p class="text-sm mb-1">拖拽文件到此处，或点击选择</p>
            <p>支持 PDF / MD / TXT</p>
          </div>
          <div v-else class="text-xs">
            <p class="text-sm font-medium text-slate-700 mb-1">{{ uploadFile.name }}</p>
            <p class="text-slate-400">{{ (uploadFile.size / 1024).toFixed(1) }} KB</p>
          </div>
        </div>

        <!-- Progress & Result -->
        <div v-if="uploading" class="mt-3">
          <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div class="h-full bg-accent rounded-full transition-all" :style="{ width: uploadProgress + '%' }"></div>
          </div>
          <p class="text-[11px] text-slate-400 mt-1">上传中 {{ uploadProgress }}%</p>
        </div>
        <div v-if="uploadResult" class="mt-3 text-xs" :class="uploadResult.startsWith('✅') ? 'text-success' : 'text-red-500'">
          {{ uploadResult }}
        </div>

        <!-- Action buttons -->
        <div class="flex gap-2 mt-4">
          <button @click="doUpload" :disabled="!uploadFile || uploading"
            class="px-3 py-1.5 text-xs font-medium bg-accent text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors">
            {{ uploading ? '上传中…' : '上传到知识库' }}
          </button>
          <button @click="doReload" :disabled="reloading"
            class="px-3 py-1.5 text-xs font-medium border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 disabled:opacity-40 transition-colors">
            {{ reloading ? '加载中…' : '重新加载全部' }}
          </button>
        </div>
        <div v-if="reloadResult" class="mt-2 text-xs" :class="reloadResult.startsWith('✅') ? 'text-success' : 'text-red-500'">
          {{ reloadResult }}
        </div>
      </div>

      <!-- Intent distribution -->
      <div class="bg-white rounded-lg border border-slate-200 p-5">
        <h3 class="text-xs font-semibold text-slate-500 uppercase mb-4">意图分布</h3>
        <div class="space-y-2">
          <div v-for="item in intentDistribution" :key="item.intent" class="flex items-center gap-3">
            <span class="text-xs text-slate-600 w-16">{{ item.label }}</span>
            <div class="flex-1 h-5 bg-slate-50 rounded-full overflow-hidden">
              <div
                :class="item.color"
                class="h-full rounded-full flex items-center justify-end pr-2 transition-all"
                :style="{ width: `${(item.count / maxCount) * 100}%` }"
              >
                <span class="text-[10px] text-white font-medium">{{ item.count.toLocaleString() }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent sessions -->
      <div class="bg-white rounded-lg border border-slate-200">
        <div class="px-5 py-3 border-b border-slate-100">
          <h3 class="text-xs font-semibold text-slate-500 uppercase">最近会话</h3>
        </div>
        <table class="w-full text-xs">
          <thead>
            <tr class="text-slate-400 border-b border-slate-100">
              <th class="text-left px-5 py-2 font-medium">会话 ID</th>
              <th class="text-left px-5 py-2 font-medium">用户</th>
              <th class="text-left px-5 py-2 font-medium">意图</th>
              <th class="text-left px-5 py-2 font-medium">消息数</th>
              <th class="text-left px-5 py-2 font-medium">时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in recentSessions" :key="s.id" class="border-b border-slate-50 hover:bg-slate-50">
              <td class="px-5 py-2.5 font-mono text-slate-500">{{ s.id }}</td>
              <td class="px-5 py-2.5">{{ s.user }}</td>
              <td class="px-5 py-2.5">
                <span :class="[
                  'px-1.5 py-0.5 rounded text-[10px] font-medium',
                  s.intent === 'qa' ? 'bg-accent-soft text-accent' :
                  s.intent === 'troubleshoot' ? 'bg-amber-50 text-amber-700' :
                  s.intent === 'consumables' ? 'bg-emerald-50 text-emerald-700' :
                  'bg-slate-100 text-slate-600'
                ]">{{ intentLabels[s.intent] || s.intent }}</span>
              </td>
              <td class="px-5 py-2.5 text-slate-500">{{ s.messages }}</td>
              <td class="px-5 py-2.5 text-slate-400">{{ s.time }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
