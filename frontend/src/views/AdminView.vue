<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getKnowledgeStatus, uploadKnowledgeFile, reloadKnowledge, getBm25Status, rebuildBm25, getKnowledgeFiles, type KnowledgeStatus, type KnowledgeFile } from '@/api'

const kb = ref<KnowledgeStatus | null>(null)
const files = ref<KnowledgeFile[]>([])
const uploadFile = ref<File | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadResult = ref('')
const reloading = ref(false)
const reloadResult = ref('')
const kbLoading = ref(false)
const dragging = ref(false)

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

async function loadFiles() {
  try { const res = await getKnowledgeFiles(); files.value = res.files } catch { /* */ }
}

onMounted(() => { loadStatus(); loadBm25Status(); loadFiles() })
</script>

<template>
  <div class="flex flex-col h-full">
    <header class="flex items-center px-6 py-3 bg-surface border-b border-neutral-200 shrink-0">
      <div>
        <h1 class="text-sm font-semibold text-neutral-800">管理后台</h1>
        <p class="text-[11px] text-neutral-400 mt-0.5">知识库管理</p>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-6 space-y-5">
      <!-- 向量库状态 -->
      <div class="bg-surface border border-neutral-200 rounded-xl p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-xs font-semibold text-neutral-500 uppercase tracking-wider">向量知识库</h3>
          <button @click="loadStatus" class="text-[11px] text-accent hover:underline">刷新</button>
        </div>

        <div v-if="kbLoading" class="text-xs text-neutral-400">加载中...</div>
        <template v-else-if="kb">
          <div class="flex items-center gap-4 mb-4 text-xs text-neutral-600">
            <span>集合: <code class="text-neutral-800 font-mono">{{ kb.collection || '-' }}</code></span>
            <span>文档数: <strong>{{ kb.total_documents ?? '?' }}</strong></span>
            <span>维度: <strong>{{ kb.dimension ?? '?' }}</strong></span>
            <span v-if="kb.status === 'empty'" class="text-warn">知识库为空</span>
          </div>
        </template>

        <!-- 上传区 -->
        <div
          @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop"
          @click="($refs.fileInput as any)?.click()"
          :class="['border-2 border-dashed rounded-xl p-6 text-center transition-base cursor-pointer',
            dragging ? 'border-accent bg-accent-soft/30' : 'border-neutral-200 hover:border-neutral-300']"
        >
          <input ref="fileInput" type="file" accept=".pdf,.md,.txt" class="hidden" @change="onFileSelected" />
          <div v-if="!uploadFile" class="text-xs text-neutral-400">
            <p class="text-sm text-neutral-500 mb-1">拖拽文件上传，或点击选择</p>
            <p>支持 PDF / Markdown / 文本</p>
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

      <!-- 已上传文件 -->
      <div class="bg-surface border border-neutral-200 rounded-xl p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-xs font-semibold text-neutral-500 uppercase tracking-wider">已上传文件</h3>
          <button @click="loadFiles" class="text-[11px] text-accent hover:underline">刷新</button>
        </div>
        <div v-if="files.length === 0" class="text-xs text-neutral-400">暂无上传文件</div>
        <div v-else class="space-y-1.5">
          <div v-for="f in files" :key="f.filename"
            class="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-neutral-50 transition-base"
          >
            <div class="flex items-center gap-3 min-w-0">
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-500">{{ f.file_type }}</span>
              <span class="text-xs text-neutral-700 truncate">{{ f.filename }}</span>
              <span v-if="f.source === 'filesystem'" class="text-[10px] text-neutral-400" title="手动放入目录，未通过 API 上传">本地</span>
            </div>
            <div class="flex items-center gap-3 text-[11px] text-neutral-400 shrink-0">
              <span v-if="f.chunks > 0">{{ f.chunks }} 片段</span>
              <span v-if="f.uploaded_at">{{ new Date(f.uploaded_at).toLocaleDateString('zh-CN') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- BM25 -->
      <div class="bg-surface border border-neutral-200 rounded-xl p-6">
        <h3 class="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-4">BM25 关键词索引</h3>
        <template v-if="bm25Status">
          <div class="flex items-center gap-4 mb-3 text-xs text-neutral-600">
            <span>文档: <strong>{{ bm25Status.doc_count ?? 0 }}</strong></span>
            <span>词项: <strong>{{ bm25Status.terms ?? 0 }}</strong></span>
            <span>构建时间: <code class="text-neutral-700 font-mono">{{ bm25Status.built_at || '未构建' }}</code></span>
          </div>
          <div v-if="bm25StaleTip" class="p-3 bg-warn-soft border border-amber-200 rounded-lg mb-3 text-xs text-amber-800">
            索引可能已过时，建议重建。
          </div>
          <button @click="doRebuildBm25" :disabled="bm25Rebuilding"
            class="px-4 py-2 text-xs font-medium bg-accent text-white rounded-lg hover:bg-accent-hover disabled:opacity-40 transition-base">
            {{ bm25Rebuilding ? '重建中...' : '重建索引' }}
          </button>
          <div v-if="bm25RebuildResult" class="mt-2 text-xs text-success">{{ bm25RebuildResult }}</div>
        </template>
      </div>
    </div>
  </div>
</template>
