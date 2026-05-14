<template>
  <div class="kb-page">

    <!-- Hero / Stats -->
    <div class="kb-hero">
      <div class="hero-inner">
        <div class="hero-left">
          <div class="hero-icon-wrap">
            <Database :size="22" />
          </div>
          <div>
            <h1 class="hero-title">知识库管理</h1>
            <p class="hero-sub">上传教辅材料，AI 自动提取题目并向量化索引，赋能出题检索</p>
          </div>
        </div>
        <div class="stats-row">
          <div class="stat-item">
            <span class="stat-val">{{ documents.length }}</span>
            <span class="stat-key">教辅来源</span>
          </div>
          <div class="stat-div"></div>
          <div class="stat-item">
            <span class="stat-val">{{ totalQuestions }}</span>
            <span class="stat-key">知识片段</span>
          </div>
          <div class="stat-div"></div>
          <div class="stat-item">
            <span class="stat-val stat-engine">MinerU VLM</span>
            <span class="stat-key">解析引擎</span>
          </div>
        </div>
      </div>
    </div>

    <div class="kb-body">

      <!-- Upload section -->
      <section class="upload-section">
        <div class="section-label">
          <UploadCloud :size="14" />
          <span>上传文件</span>
        </div>

        <div
          class="drop-zone"
          :class="{ dragging: isDragging }"
          @dragenter.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @dragover.prevent
          @drop.prevent="onDrop"
          @click="fileInputEl.click()"
        >
          <input
            ref="fileInputEl"
            type="file"
            multiple
            accept=".pdf"
            class="hidden-input"
            @change="onFileSelect"
          />
          <div class="drop-icon-ring">
            <UploadCloud :size="28" />
          </div>
          <p class="drop-title">拖拽 PDF 到此处，或<span class="drop-cta">点击选择文件</span></p>
          <p class="drop-hint">支持批量上传 · 单文件 ≤ 10 MB · MinerU 自动识别题目边界</p>
        </div>

        <!-- Pending queue -->
        <div v-if="uploadQueue.length > 0" class="queue-list">
          <div v-for="(f, i) in uploadQueue" :key="i" class="queue-item">
            <FileText :size="14" class="queue-icon" />
            <span class="queue-name">{{ f.name }}</span>
            <span class="queue-size">{{ (f.size / 1024).toFixed(0) }} KB</span>
            <Loader2 :size="13" class="spin queue-spin" />
          </div>
        </div>
      </section>

      <!-- Document library -->
      <section class="doc-section">
        <div class="section-label">
          <BookOpen :size="14" />
          <span>已入库文件</span>
          <button class="refresh-btn" @click="loadDocuments" title="刷新">
            <RefreshCw :size="13" :class="{ spin: isLoading }" />
          </button>
        </div>

        <div v-if="isLoading && documents.length === 0" class="doc-loading">
          <Loader2 :size="22" class="spin" />
          <span>加载中...</span>
        </div>

        <div v-else-if="documents.length === 0" class="doc-empty">
          <div class="doc-empty-icon-wrap">
            <BookOpen :size="30" />
          </div>
          <p class="doc-empty-title">暂无入库文件</p>
          <p class="doc-empty-sub">上传教辅 PDF 后，AI 将自动提取并索引每道题目</p>
        </div>

        <div v-else class="doc-list">
          <div v-for="doc in documents" :key="doc.source_file" class="doc-card animate-fade-in">
            <div class="doc-card-icon">
              <FileText :size="20" />
            </div>
            <div class="doc-card-body">
              <p class="doc-card-name" :title="doc.source_file">{{ doc.source_file }}</p>
              <p class="doc-card-meta">
                <span class="meta-badge">{{ doc.question_count }} 个片段</span>
                <span v-if="doc.created_at" class="meta-date">{{ formatDate(doc.created_at) }}</span>
              </p>
            </div>
            <button
              class="doc-del-btn"
              @click="deleteDocument(doc.source_file)"
              title="删除此来源"
            >
              <Trash2 :size="15" />
            </button>
          </div>
        </div>
      </section>

    </div>

    <!-- Processing overlay -->
    <Teleport to="body">
      <Transition name="overlay">
        <div v-if="processing" class="process-overlay">
          <div class="process-panel">
            <p class="process-filename">{{ processing.filename }}</p>

            <!-- SVG progress ring -->
            <div class="ring-wrap" :class="{ success: processing.stage === 'done', error: processing.stage === 'error' }">
              <svg class="ring-svg" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" fill="none" stroke-width="6" class="ring-track" />
                <circle
                  cx="60" cy="60" r="50" fill="none" stroke-width="6"
                  class="ring-fill"
                  :stroke-dasharray="ringCircumference"
                  :stroke-dashoffset="ringDashOffset"
                  stroke-linecap="round"
                />
              </svg>
              <div class="ring-center-content">
                <CheckCircle2 v-if="processing.stage === 'done'" :size="30" class="ring-check" />
                <AlertCircle v-else-if="processing.stage === 'error'" :size="30" class="ring-err-icon" />
                <span v-else class="ring-pct">{{ Math.round((processing.progress || 0) * 100) }}%</span>
              </div>
            </div>

            <p class="process-msg">{{ processing.msg }}</p>
            <p v-if="processing.pages" class="process-pages">{{ processing.pages }} 页</p>

            <div v-if="processing.stage === 'done'" class="process-done-info">
              共入库 <strong>{{ processing.questionCount }}</strong> 个知识片段
              <template v-if="processing.skippedCount > 0">
                <br/><span class="dedup-note">跳过 {{ processing.skippedCount }} 道已有重复题目</span>
              </template>
            </div>
            <div v-if="processing.stage === 'error'" class="process-err-info">
              {{ processing.errorMsg }}
            </div>

            <!-- Stage timeline -->
            <div class="stage-bar">
              <div
                v-for="s in stages"
                :key="s.key"
                class="stage-dot"
                :class="{
                  active: processing.stage === s.key,
                  done: stageOrder.indexOf(processing.stage) > stageOrder.indexOf(s.key),
                  error: processing.stage === 'error',
                }"
                :title="s.label"
              ></div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Delete confirm dialog -->
    <Teleport to="body">
      <Transition name="overlay">
        <div v-if="confirmDialog.show" class="process-overlay" @click.self="confirmDialog.resolve(false)">
          <div class="confirm-panel">
            <div class="confirm-icon-wrap">
              <Trash2 :size="22" />
            </div>
            <p class="confirm-title">确认删除</p>
            <p class="confirm-body">
              将删除 <strong>{{ confirmDialog.sourceFile }}</strong> 的所有知识片段及配图，操作不可撤销。
            </p>
            <div class="confirm-actions">
              <button class="confirm-btn-cancel" @click="confirmDialog.resolve(false)">取消</button>
              <button class="confirm-btn-ok" @click="confirmDialog.resolve(true)">确认删除</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Success toast -->
    <Teleport to="body">
      <Transition name="toast">
        <div v-if="successMsg" class="success-toast">
          <CheckCircle2 :size="16" />
          <span>{{ successMsg }}</span>
        </div>
      </Transition>
    </Teleport>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  Database, UploadCloud, FileText, Trash2, Loader2,
  CheckCircle2, AlertCircle, RefreshCw, BookOpen,
} from 'lucide-vue-next'

const API_BASE = 'http://localhost:8000'

/* ===== State ===== */
const documents = ref([])
const isLoading = ref(false)
const isDragging = ref(false)
const uploadQueue = ref([])
const processing = ref(null)
const successMsg = ref('')
const fileInputEl = ref(null)
const confirmDialog = ref({ show: false, sourceFile: '', resolve: null })

function showConfirm(sourceFile) {
  return new Promise(resolve => {
    confirmDialog.value = { show: true, sourceFile, resolve: (v) => {
      confirmDialog.value.show = false
      resolve(v)
    }}
  })
}

/* ===== Stats ===== */
const totalQuestions = computed(() => documents.value.reduce((s, d) => s + d.question_count, 0))

/* ===== Ring maths ===== */
const RING_R = 50
const ringCircumference = 2 * Math.PI * RING_R  // ≈ 314.16

const ringDashOffset = computed(() => {
  const p = processing.value?.progress ?? 0
  return ringCircumference * (1 - p)
})

/* ===== Stage metadata ===== */
const stages = [
  { key: 'submit',     label: '提交任务' },
  { key: 'uploading',  label: '上传文件' },
  { key: 'parsing',    label: 'MinerU 解析' },
  { key: 'downloading',label: '下载结果' },
  { key: 'splitting',  label: '题目切分' },
  { key: 'embedding',  label: '向量化' },
  { key: 'dedup',      label: '去重检测' },
  { key: 'done',       label: '完成' },
]
const stageOrder = stages.map(s => s.key)

/* ===== Data loading ===== */
async function loadDocuments() {
  isLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/knowledge/documents`)
    const data = await res.json()
    if (data.code === 0) documents.value = data.data
  } catch (e) {
    console.error('加载文档列表失败:', e)
  } finally {
    isLoading.value = false
  }
}

/* ===== Upload handlers ===== */
function onDrop(e) {
  isDragging.value = false
  const files = [...e.dataTransfer.files].filter(
    f => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
  )
  if (files.length) enqueueFiles(files)
}

function onFileSelect(e) {
  const files = [...e.target.files]
  if (files.length) enqueueFiles(files)
  e.target.value = ''
}

function enqueueFiles(files) {
  uploadQueue.value.push(...files)
  if (!processing.value) processNextFile()
}

async function processNextFile() {
  if (uploadQueue.value.length === 0) return

  const file = uploadQueue.value.shift()

  processing.value = {
    filename: file.name,
    stage: 'init',
    progress: 0,
    msg: '准备中...',
    pages: '',
    questionCount: 0,
    skippedCount: 0,
    duplicateTitles: [],
    errorMsg: '',
  }

  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await fetch(`${API_BASE}/upload_knowledge`, { method: 'POST', body: formData })
    if (!res.ok) throw new Error(`服务器错误 HTTP ${res.status}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let finished = false

    while (!finished) {
      const { done, value } = await reader.read()
      if (done) break

      const lines = decoder.decode(value, { stream: true }).split('\n\n')
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        let event
        try { event = JSON.parse(line.substring(6)) } catch { continue }

        processing.value.stage = event.stage
        processing.value.msg = event.msg
        processing.value.progress = event.progress ?? 0
        if (event.pages) processing.value.pages = event.pages

        if (event.stage === 'done') {
          processing.value.questionCount = event.question_count || 0
          processing.value.skippedCount = event.skipped_count || 0
          processing.value.duplicateTitles = event.duplicate_titles || []
          await new Promise(r => setTimeout(r, 2200))
          const qc = processing.value.questionCount
          const skipped = processing.value.skippedCount
          const fname = file.name.length > 20 ? file.name.slice(0, 20) + '...' : file.name
          processing.value = null
          let toastMsg = `入库成功 · ${fname} · ${qc} 个知识片段`
          if (skipped > 0) toastMsg += ` · 跳过 ${skipped} 道重复`
          successMsg.value = toastMsg
          setTimeout(() => { successMsg.value = '' }, 5000)
          await loadDocuments()
          finished = true
          break
        } else if (event.stage === 'error') {
          processing.value.errorMsg = event.msg
          await new Promise(r => setTimeout(r, 3500))
          processing.value = null
          finished = true
          break
        }
      }
    }
  } catch (e) {
    if (processing.value) {
      processing.value.stage = 'error'
      processing.value.errorMsg = e.message
      await new Promise(r => setTimeout(r, 3500))
    }
    processing.value = null
  }

  if (uploadQueue.value.length > 0) {
    await processNextFile()
  }
}

/* ===== Delete ===== */
async function deleteDocument(sourceFile) {
  const ok = await showConfirm(sourceFile)
  if (!ok) return
  try {
    const res = await fetch(
      `${API_BASE}/knowledge/documents/${encodeURIComponent(sourceFile)}`,
      { method: 'DELETE' }
    )
    const data = await res.json()
    if (data.code === 0) {
      successMsg.value = data.msg
      setTimeout(() => { successMsg.value = '' }, 4000)
      await loadDocuments()
    } else {
      successMsg.value = '删除失败: ' + data.msg
      setTimeout(() => { successMsg.value = '' }, 4000)
    }
  } catch (e) {
    console.error('删除失败:', e)
  }
}

/* ===== Utilities ===== */
function formatDate(ts) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

onMounted(loadDocuments)
</script>

<style scoped>
/* ===== Page layout ===== */
.kb-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-deep);
  overflow: hidden;
}

/* ===== Hero ===== */
.kb-hero {
  flex-shrink: 0;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-sub);
  padding: 24px 40px;
}

.hero-inner {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}

.hero-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.hero-icon-wrap {
  width: 48px;
  height: 48px;
  background: var(--violet-dim);
  border: 1px solid rgba(139,127,245,0.4);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--violet-hi);
  flex-shrink: 0;
}

.hero-title {
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-bright);
  margin: 0 0 4px;
}

.hero-sub {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.stats-row {
  display: flex;
  align-items: center;
  gap: 20px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-sub);
  border-radius: 14px;
  padding: 14px 24px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
}

.stat-val {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-bright);
  font-family: var(--font-mono);
  line-height: 1;
}

.stat-engine {
  font-size: 14px;
  font-family: var(--font-ui);
  color: var(--violet-hi);
}

.stat-key {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.stat-div {
  width: 1px;
  height: 32px;
  background: var(--border-sub);
}

/* ===== Body ===== */
.kb-body {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
  display: flex;
  flex-direction: column;
  gap: 32px;
  max-width: 1100px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

/* ===== Section label ===== */
.section-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 14px;
}

.refresh-btn {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  padding: 4px;
  border-radius: 5px;
  transition: color 0.12s;
}

.refresh-btn:hover { color: var(--text-sec); }

/* ===== Drop zone ===== */
.drop-zone {
  border: 2px dashed var(--border-hi);
  border-radius: 18px;
  padding: 48px 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.drop-zone:hover,
.drop-zone.dragging {
  border-color: var(--violet);
  background: var(--violet-glow);
}

.drop-zone.dragging {
  border-style: solid;
  box-shadow: 0 0 0 4px rgba(139,127,245,0.12);
}

.hidden-input { display: none; }

.drop-icon-ring {
  width: 64px;
  height: 64px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--violet-hi);
  margin-bottom: 4px;
}

.drop-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-pri);
  margin: 0;
}

.drop-cta {
  color: var(--violet-hi);
  text-decoration: underline;
  text-decoration-color: rgba(139,127,245,0.5);
}

.drop-hint {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

/* ===== Queue list ===== */
.queue-list {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 14px;
}

.queue-icon { color: var(--violet-hi); flex-shrink: 0; }

.queue-name {
  flex: 1;
  color: var(--text-pri);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.queue-size {
  font-size: 13px;
  color: var(--text-muted);
  flex-shrink: 0;
  font-family: var(--font-mono);
}

.queue-spin { color: var(--amber); flex-shrink: 0; }

/* ===== Document list ===== */
.doc-loading {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 32px;
  color: var(--text-muted);
  font-size: 15px;
}

.doc-empty {
  text-align: center;
  padding: 60px 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.doc-empty-icon-wrap {
  width: 64px;
  height: 64px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-sub);
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.doc-empty-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-sec);
  margin: 0;
}

.doc-empty-sub {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.doc-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.doc-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-sub);
  border-radius: 14px;
  padding: 16px 18px;
  transition: border-color 0.15s, background 0.15s;
}

.doc-card:hover {
  border-color: var(--border-hi);
  background: var(--bg-elevated);
}

.doc-card-icon {
  width: 42px;
  height: 42px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--violet-hi);
  flex-shrink: 0;
}

.doc-card-body {
  flex: 1;
  min-width: 0;
}

.doc-card-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-pri);
  margin: 0 0 5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-card-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
}

.meta-badge {
  font-size: 13px;
  font-weight: 600;
  color: var(--violet-hi);
  background: rgba(139,127,245,0.1);
  border: 1px solid rgba(139,127,245,0.2);
  border-radius: 6px;
  padding: 2px 8px;
}

.meta-date {
  font-size: 13px;
  color: var(--text-muted);
}

.doc-del-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 9px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: all 0.14s;
  opacity: 0;
}

.doc-card:hover .doc-del-btn { opacity: 1; }

.doc-del-btn:hover {
  background: rgba(244,63,94,0.1);
  border-color: rgba(244,63,94,0.3);
  color: #f87171;
}

/* ===== Processing overlay ===== */
.process-overlay {
  position: fixed;
  inset: 0;
  background: rgba(9,9,15,0.82);
  backdrop-filter: blur(6px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.process-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 40px 48px;
  min-width: 340px;
  max-width: 440px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  box-shadow: 0 40px 80px rgba(0,0,0,0.6);
}

.process-filename {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-sec);
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0;
}

/* Ring */
.ring-wrap {
  position: relative;
  width: 140px;
  height: 140px;
}

.ring-svg {
  width: 140px;
  height: 140px;
  transform: rotate(-90deg);
}

.ring-track {
  stroke: var(--bg-elevated);
}

.ring-fill {
  stroke: var(--violet);
  transition: stroke-dashoffset 0.5s ease, stroke 0.4s ease;
}

.ring-wrap.success .ring-fill { stroke: var(--green); }
.ring-wrap.error .ring-fill { stroke: #f43f5e; }

.ring-center-content {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ring-pct {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-bright);
  font-family: var(--font-mono);
}

.ring-check { color: var(--green); }
.ring-err-icon { color: #f43f5e; }

.process-msg {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-pri);
  text-align: center;
  margin: 0;
}

.process-pages {
  font-size: 13px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  margin: 0;
}

.process-done-info {
  font-size: 14px;
  color: var(--green);
  text-align: center;
  background: rgba(34,197,94,0.08);
  border: 1px solid rgba(34,197,94,0.2);
  border-radius: 10px;
  padding: 10px 18px;
}

.dedup-note {
  font-size: 13px;
  color: var(--amber);
  display: inline-block;
  margin-top: 4px;
}

.process-err-info {
  font-size: 13px;
  color: #f87171;
  text-align: center;
  background: rgba(244,63,94,0.08);
  border: 1px solid rgba(244,63,94,0.2);
  border-radius: 10px;
  padding: 10px 18px;
  max-width: 100%;
  word-break: break-word;
}

/* Stage dots */
.stage-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.stage-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border-hi);
  transition: background 0.3s, transform 0.2s;
}

.stage-dot.done { background: var(--violet-dim); }
.stage-dot.active {
  background: var(--violet);
  transform: scale(1.35);
  box-shadow: 0 0 8px rgba(139,127,245,0.6);
}
.stage-dot.error { background: #f43f5e; }

/* ===== Confirm dialog ===== */
.confirm-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 36px 40px 28px;
  width: 400px;
  max-width: calc(100vw - 48px);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  box-shadow: 0 40px 80px rgba(0,0,0,0.6);
}

.confirm-icon-wrap {
  width: 52px;
  height: 52px;
  background: rgba(244,63,94,0.1);
  border: 1px solid rgba(244,63,94,0.25);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f87171;
  margin-bottom: 4px;
}

.confirm-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-bright);
  margin: 0;
}

.confirm-body {
  font-size: 14px;
  color: var(--text-sec);
  text-align: center;
  line-height: 1.6;
  margin: 0 0 8px;
}

.confirm-body strong {
  color: var(--text-pri);
  word-break: break-all;
}

.confirm-actions {
  display: flex;
  gap: 10px;
  width: 100%;
}

.confirm-btn-cancel,
.confirm-btn-ok {
  flex: 1;
  height: 40px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid;
  transition: all 0.14s;
}

.confirm-btn-cancel {
  background: transparent;
  border-color: var(--border-hi);
  color: var(--text-sec);
}
.confirm-btn-cancel:hover {
  background: var(--bg-elevated);
  color: var(--text-pri);
}

.confirm-btn-ok {
  background: rgba(244,63,94,0.12);
  border-color: rgba(244,63,94,0.35);
  color: #f87171;
}
.confirm-btn-ok:hover {
  background: rgba(244,63,94,0.22);
  border-color: rgba(244,63,94,0.6);
  color: #fca5a5;
}

/* ===== Success toast ===== */
.success-toast {
  position: fixed;
  bottom: 32px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2000;
  display: flex;
  align-items: center;
  gap: 9px;
  background: var(--bg-elevated);
  border: 1px solid rgba(34,197,94,0.35);
  border-radius: 30px;
  padding: 12px 22px;
  font-size: 15px;
  font-weight: 600;
  color: var(--green);
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  white-space: nowrap;
  pointer-events: none;
}

/* ===== Transitions ===== */
.overlay-enter-active { transition: opacity 0.22s ease; }
.overlay-leave-active { transition: opacity 0.18s ease; }
.overlay-enter-from,
.overlay-leave-to { opacity: 0; }
.overlay-enter-active .process-panel {
  animation: panelIn 0.28s cubic-bezier(0.34,1.56,0.64,1);
}
@keyframes panelIn {
  from { transform: scale(0.88) translateY(16px); opacity: 0; }
  to   { transform: scale(1) translateY(0); opacity: 1; }
}

.toast-enter-active { transition: all 0.3s cubic-bezier(0.34,1.56,0.64,1); }
.toast-leave-active { transition: all 0.2s ease; }
.toast-enter-from,
.toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(12px); }

/* ===== Utils ===== */
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
