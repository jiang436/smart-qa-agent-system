<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getKnowledgeStatus, uploadKnowledgeFile, reloadKnowledge, getBm25Status, rebuildBm25, type KnowledgeStatus } from '@/api'

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
  { intent: 'general', label: '其他', count: 830, color: 'bg-neutral-400' },
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
  qa: '知识问答', troubleshoot: '故障排查', consumables: '耗材管理', general: '综合',
}

const intentBadgeColors: Record<string, string> = {
  qa: 'bg-accent-soft text-accent',
  troubleshoot: 'bg-amber-50 text-amber-700',
  consumables: 'bg-emerald-50 text-emerald-700',
  general: 'bg-neutral-100 text-neutral-600',
}

// Knowledge
const kb = ref<KnowledgeStatus | null>(null)
const uploadFile = ref<File | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadResult = ref('')
const reloading = ref(false)
const reloadResult = ref('')
const kbLoading = ref(false)
const dragging = ref(false)

// BM25
const bm25Status = ref<any>(null)
const bm25Loading = ref(false)
const bm25Rebuilding = ref(false)
const bm25RebuildResult = ref('')
const bm25StaleTip = ref(false)

async function loadStatus() {
  kbLoading.value = true
  try { kb.value = await getKnowledgeStatus() } catch { /* */ }
  kbLoading.value = false
}

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) { uploadFile.value = input.files[0]; uploadResult.value = '' }
}

async function doUpload() {
  if (!uploadFile.value) return
  uploading.value = true; uploadProgress.value = 0; uploadResult.value = ''
  try {
    const res = await uploadKnowledgeFile(uploadFile.value, (pct) => { uploadProgress.value = pct })
    uploadResult.value = `上传成功: ${res.chunks} 个片段，维度 ${res.dimension}`
    uploadFile.value = null; loadStatus()
  } catch (e: any) { uploadResult.value = e.message || '上传失败' }
  uploading.value = false
}

async function doReload() {
  if (!confirm('确认重新加载全部知识库？')) return
  reloading.value = true; reloadResult.value = ''
  try { const res = await reloadKnowledge(); reloadResult.value = res.message || '完成'; loadStatus() }
  catch (e: any) { reloadResult.value = e.message || '失败' }
  reloading.value = false
}

function onDragOver(e: DragEvent) { e.preventDefault(); dragging.value = true }
function onDragLeave() { dragging.value = false }
function onDrop(e: DragEvent) {
  e.preventDefault(); dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) { uploadFile.value = file; uploadResult.value = '' }
}

async function loadBm25Status() {
  bm25Loading.value = true
  try {
    const res = await getBm25Status(); bm25Status.value = res
    if (res.built_at) { const h = (Date.now() - new Date(res.built_at.replace(' ', 'T')).getTime()) / 3600000; bm25StaleTip.value = h > 1 }
  } catch { /* */ }
  bm25Loading.value = false
}

async function doRebuildBm25() {
  bm25Rebuilding.value = true; bm25RebuildResult.value = ''
  try { const res = await rebuildBm25(); bm25Status.value = res; bm25RebuildResult.value = `完成: ${res.doc_count} 篇文档`; bm25StaleTip.value = false }
  catch (e: any) { bm25RebuildResult.value = e.message || '失败' }
  bm25Rebuilding.value = false
}

onMounted(() => { loadStatus(); loadBm25Status() })
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center px-6 py-3 bg-surface border-b border-neutral-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-neutral-800">管理后台</h1>
        <p class="text-[11px] text-neutral-400 mt-0.5">系统运行状态 - 知识库管理</p>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-6 space-y-5">
      <!-- Metrics -->
      <div class="grid grid-cols-5 gap-3">
        <div v-for="m in [
          { val: metrics.totalRequests.toLocaleString(), label: '总请求数', cls: '' },
          { val: `${metrics.avgLatency}s`, label: '平均延迟', cls: '' },
          { val: `${metrics.cacheHitRate}%`, label: '缓存命中率', cls: 'text-success' },
          { val: metrics.activeSessions, label: '活跃会话', cls: '' },
          { val: `${metrics.errorRate}%`, label: '错误率', cls: 'text-amber-500' },
        ]" :key="m.label" class="bg-surface border border-neutral-200 rounded-xl p-5">
          <div :class="['text-2xl font-bold', m.cls || 'text-neutral-800']">{{ m.val }}</div>
          <div class="text-[11px] text-neutral-400 mt-1">{{ m.label }}</div>
        </div>
      </div>

      <!-- Knowledge Base -->
      <div class="bg-surface border border-neutral-200 rounded-xl p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-xs font-semibold text-neutral-500 uppercase tracking-wider">知识库管理</h3>
          <button @click="loadStatus" class="text-[11px] text-accent hover:underline">刷新</button>
        </div>

        <div v-if="kbLoading" class="text-xs text-neutral-400">加载中...</div>
        <template v-else-if="kb">
          <div class="flex items-center gap-4 mb-4 text-xs text-neutral-600">
            <span>向量库: <code class="text-neutral-800 font-mono">{{ kb.collection || '-' }}</code></span>
            <span>文档数: <strong>{{ kb.total_documents ?? '?' }}</strong></span>
            <span>维度: <strong>{{ kb.dimension ?? '?' }}</strong></span>
            <span v-if="kb.status === 'empty'" class="text-amber-500">（知识库为空）</span>
          </div>
        </template>

        <div
          @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop"
          @click="($refs.fileInput as any)?.click()"
          :class="['border-2 border-dashed rounded-xl p-6 text-center transition-base cursor-pointer',
            dragging ? 'border-accent bg-accent-soft/30' : 'border-neutral-200 hover:border-neutral-300']"
        >
          <input ref="fileInput" type="file" accept=".pdf,.md,.txt" class="hidden" @change="onFileSelected" />
          <div v-if="!uploadFile" class="text-xs text-neutral-400">
            <p class="text-sm text-neutral-500 mb-1">拖拽文件到此处，或点击选择</p>
            <p>支持 PDF / Markdown / 文本文件</p>
          </div>
          <div v-else class="text-xs">
            <p class="text-sm font-medium text-neutral-700 mb-1">{{ uploadFile.name }}</p>
            <p class="text-neutral-400">{{ (uploadFile.size / 1024).toFixed(1) }} KB</p>
          </div>
        </div>

        <div v-if="uploading" class="mt-3">
          <div class="h-1.5 bg-neutral-100 rounded-full overflow-hidden">
            <div class="h-full bg-accent rounded-full transition-base" :style="{ width: uploadProgress + '%' }" />
          </div>
          <p class="text-[11px] text-neutral-400 mt-1">上传中 {{ uploadProgress }}%</p>
        </div>
        <div v-if="uploadResult" :class="['mt-3 text-xs', uploadResult.startsWith('上传成功') ? 'text-success' : 'text-red-500']">{{ uploadResult }}</div>

        <div class="flex gap-2.5 mt-4">
          <button @click="doUpload" :disabled="!uploadFile || uploading"
            class="px-4 py-2 text-xs font-medium bg-accent text-white rounded-lg hover:bg-accent-hover disabled:opacity-40 transition-base">
            {{ uploading ? '上传中...' : '上传到知识库' }}
          </button>
          <button @click="doReload" :disabled="reloading"
            class="px-4 py-2 text-xs font-medium border border-neutral-200 text-neutral-600 rounded-lg hover:bg-neutral-50 disabled:opacity-40 transition-base">
            {{ reloading ? '加载中...' : '重新加载全部' }}
          </button>
        </div>
      </div>

      <!-- BM25 -->
      <div class="bg-surface border border-neutral-200 rounded-xl p-6">
        <h3 class="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-4">BM25 关键词索引</h3>
        <template v-if="bm25Status">
          <div class="flex items-center gap-4 mb-3 text-xs text-neutral-600">
            <span>文档: <strong>{{ bm25Status.doc_count ?? 0 }}</strong></span>
            <span>词项: <strong>{{ bm25Status.terms ?? 0 }}</strong></span>
            <span>构建: <code class="text-neutral-700 font-mono">{{ bm25Status.built_at || '未构建' }}</code></span>
          </div>
          <div v-if="bm25StaleTip" class="p-3 bg-warn-soft border border-amber-200 rounded-lg mb-3 text-xs text-amber-800">
            索引可能已过时，建议重建以确保检索准确。
          </div>
          <button @click="doRebuildBm25" :disabled="bm25Rebuilding"
            class="px-4 py-2 text-xs font-medium bg-accent text-white rounded-lg hover:bg-accent-hover disabled:opacity-40 transition-base">
            {{ bm25Rebuilding ? '重建中...' : '重建索引' }}
          </button>
          <div v-if="bm25RebuildResult" class="mt-2 text-xs text-success">{{ bm25RebuildResult }}</div>
        </template>
      </div>

      <!-- Intent distribution -->
      <div class="bg-surface border border-neutral-200 rounded-xl p-6">
        <h3 class="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-4">意图分布</h3>
        <div class="space-y-2.5">
          <div v-for="item in intentDistribution" :key="item.intent" class="flex items-center gap-3">
            <span class="text-xs text-neutral-600 w-20">{{ item.label }}</span>
            <div class="flex-1 h-5 bg-neutral-100 rounded-full overflow-hidden">
              <div :class="item.color" class="h-full rounded-full flex items-center justify-end pr-2 transition-base"
                :style="{ width: `${(item.count / maxCount) * 100}%` }">
                <span class="text-[10px] text-white font-medium">{{ item.count.toLocaleString() }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent sessions -->
      <div class="bg-surface border border-neutral-200 rounded-xl overflow-hidden">
        <div class="px-6 py-4 border-b border-neutral-100">
          <h3 class="text-xs font-semibold text-neutral-500 uppercase tracking-wider">最近会话</h3>
        </div>
        <table class="w-full text-xs">
          <thead>
            <tr class="text-neutral-400 border-b border-neutral-100">
              <th class="text-left px-6 py-2.5 font-medium">会话 ID</th>
              <th class="text-left px-6 py-2.5 font-medium">用户</th>
              <th class="text-left px-6 py-2.5 font-medium">意图</th>
              <th class="text-left px-6 py-2.5 font-medium">消息数</th>
              <th class="text-left px-6 py-2.5 font-medium">时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in recentSessions" :key="s.id" class="border-b border-neutral-50 hover:bg-neutral-50 transition-base">
              <td class="px-6 py-3 font-mono text-neutral-500">{{ s.id }}</td>
              <td class="px-6 py-3 text-neutral-700">{{ s.user }}</td>
              <td class="px-6 py-3">
                <span :class="['px-1.5 py-0.5 rounded-md text-[10px] font-medium', intentBadgeColors[s.intent] || intentBadgeColors.general]">
                  {{ intentLabels[s.intent] || s.intent }}
                </span>
              </td>
              <td class="px-6 py-3 text-neutral-500">{{ s.messages }}</td>
              <td class="px-6 py-3 text-neutral-400">{{ s.time }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
