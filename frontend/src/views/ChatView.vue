<template>
  <div class="chat-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <!-- New Conversation -->
      <button class="new-conv-btn" @click="createNewConversation">
        <Plus :size="15" />
        <span>新建对话</span>
      </button>

      <!-- Conversation List -->
      <div class="conv-list">
        <template v-for="group in groupedConversations" :key="group.label">
          <div class="conv-group-label">{{ group.label }}</div>
          <div
            v-for="conv in group.convs"
            :key="conv.id"
            class="conv-item"
            :class="{ active: conv.id === currentConvId }"
            @click="switchConversation(conv.id)"
            :title="conv.title"
          >
            <MessageSquare :size="13" class="conv-item-icon" />
            <span class="conv-item-title">{{ conv.title }}</span>
            <button
              class="conv-item-del"
              @click.stop="deleteConversation(conv.id)"
              title="删除"
            >
              <Trash2 :size="11" />
            </button>
          </div>
        </template>

        <div v-if="conversations.length === 0" class="conv-empty">
          暂无历史对话
        </div>
      </div>

    </aside>

    <!-- Main Chat Area -->
    <main class="chat-main">
      <div class="messages-area" ref="chatContainer">
        <!-- Welcome Screen -->
        <div v-if="chatHistory.length === 0" class="welcome-screen">
          <div class="welcome-icon">
            <BrainCircuit :size="32" />
          </div>
          <h2 class="welcome-title">教研大脑已就绪</h2>
          <p class="welcome-sub">描述你的出题需求，或上传题目图片 / PDF 参考文件</p>
          <div class="welcome-examples">
            <button v-for="ex in examples" :key="ex" class="example-btn" @click="prompt = ex">
              {{ ex }}
            </button>
          </div>
        </div>

        <!-- Messages -->
        <div class="messages-inner" v-else>
          <div v-for="(msg, index) in chatHistory" :key="index" class="animate-fade-in">
            <!-- User Message -->
            <div v-if="msg.role === 'user'" class="msg-user">
              <div class="bubble-user">
                <img v-if="msg.image" :src="msg.image" class="bubble-image" />
                <div v-if="msg.fileName" class="bubble-file-badge">
                  <FileText :size="14" />
                  <span>{{ msg.fileName }}</span>
                </div>
                <p v-if="msg.content" class="bubble-text">{{ msg.content }}</p>
              </div>
            </div>

            <!-- Agent Message -->
            <div v-if="msg.role === 'agent'" class="msg-agent">
              <div class="agent-avatar">
                <BrainCircuit :size="16" />
              </div>
              <div class="agent-content">
                <details
                  class="reasoning-block"
                  :open="msg.status === 'thinking' || msg.steps.length > 0"
                >
                  <summary class="reasoning-summary">
                    <Loader2 v-if="msg.status === 'thinking'" :size="14" class="spin" />
                    <Sparkles v-else :size="14" class="sparkle-icon" />
                    <span>{{ msg.status === 'thinking' ? '教研大脑深度思考中...' : '教研推理完成' }}</span>
                    <ChevronDown :size="14" class="chevron" />
                  </summary>

                  <div v-if="msg.steps.length > 0" class="reasoning-steps">
                    <div v-for="(step, sIdx) in msg.steps" :key="sIdx" class="step-item">
                      <div class="step-dot"></div>
                      <div class="step-body">
                        <p class="step-name">{{ getNodeName(step.node) }}</p>
                        <Markdown class="step-detail" :content="step.details" />
                      </div>
                    </div>
                  </div>
                  <div v-else class="reasoning-empty">暂无详细推理日志</div>
                </details>

                <div v-if="msg.pdf_student || msg.pdf_teacher" class="pdf-card">
                  <div class="pdf-card-header">
                    <CheckCircle2 :size="16" class="pdf-ok-icon" />
                    <span>试卷编译成功，可下载查看</span>
                  </div>
                  <div class="pdf-btns">
                    <button
                      v-if="msg.pdf_teacher"
                      class="pdf-btn primary"
                      @click="downloadPDF(`http://localhost:8000${msg.pdf_teacher}`, msg.download_name_teacher)"
                    >
                      <Download :size="15" /> 教师解析版
                    </button>
                    <button
                      v-if="msg.pdf_student"
                      class="pdf-btn secondary"
                      @click="downloadPDF(`http://localhost:8000${msg.pdf_student}`, msg.download_name_student)"
                    >
                      <Download :size="15" /> 学生空白版
                    </button>
                  </div>
                </div>

                <div v-if="msg.error" class="error-block">
                  <AlertCircle :size="15" />
                  出错了: {{ msg.error }}
                </div>
              </div>
            </div>
          </div>
          <div ref="scrollAnchor" class="scroll-anchor"></div>
        </div>
      </div>

      <!-- Input Bar -->
      <div class="input-bar">
        <!-- Attachment Preview -->
        <div v-if="imgFile" class="attachment-row">
          <div v-if="imgPreview" class="preview-wrap">
            <img :src="imgPreview" class="preview-img" />
            <button class="preview-remove" @click="clearAttach"><X :size="12" /></button>
          </div>
          <div v-else class="file-badge-wrap">
            <div class="file-badge">
              <FileText :size="15" class="file-badge-icon" />
              <span class="file-badge-name">{{ attachedFileName }}</span>
              <span class="file-badge-ext">{{ imgFile.type.includes('pdf') ? 'PDF' : '文件' }}</span>
            </div>
            <button class="preview-remove" @click="clearAttach"><X :size="12" /></button>
          </div>
        </div>

        <div class="input-row">
          <label class="attach-btn" title="上传图片或PDF（也可 Ctrl+V 粘贴）">
            <input type="file" class="hidden-input" @change="handleImage" accept="image/*,application/pdf,.pdf" />
            <Paperclip :size="18" />
          </label>

          <textarea
            v-model="prompt"
            @keydown.enter.exact.prevent="sendTask"
            @paste="handlePaste"
            placeholder="描述出题需求，支持 Ctrl+V 粘贴图片或拖入 PDF..."
            class="chat-input"
            rows="1"
            @input="autoResize"
            ref="textareaEl"
          ></textarea>

          <button
            class="send-btn"
            :class="{ processing: isProcessing }"
            @click="sendTask"
            :disabled="isProcessing || (!prompt && !imgFile)"
            :title="isProcessing ? '大模型正在生成中...' : '发送'"
          >
            <Loader2 v-if="isProcessing" :size="18" class="spin" />
            <Send v-else :size="18" />
          </button>
        </div>

        <p class="input-hint">Enter 发送 · Shift+Enter 换行 · Ctrl+V 粘贴图片 · 点击回形针上传 PDF/图片</p>
      </div>
    </main>
  </div>
</template>

<script>
// Required so <keep-alive :include="['ChatView']"> can match this component by name.
export default { name: 'ChatView' }
</script>

<script setup>
import { ref, nextTick, onMounted, onUnmounted, onActivated, onDeactivated, computed } from 'vue'
import {
  Loader2, Sparkles, ChevronDown, CheckCircle2,
  Download, Send, X, BrainCircuit, AlertCircle,
  FileText, Paperclip, Plus, MessageSquare, Trash2,
} from 'lucide-vue-next'
import Markdown from '../components/Markdown.vue'

/* ===== Chat State ===== */
const chatContainer = ref(null)
const scrollAnchor = ref(null)
const textareaEl = ref(null)
const chatHistory = ref([])
const prompt = ref('')
const imgFile = ref(null)
const imgPreview = ref(null)
const attachedFileName = ref('')
const isProcessing = ref(false)

/* ===== Conversation History ===== */
const STORAGE_KEY = 'lc-edu-conversations'
const conversations = ref([])
const currentConvId = ref(null)
const groupedConversations = computed(() => {
  const now = Date.now()
  const todayStart = new Date(); todayStart.setHours(0,0,0,0)
  const ydayStart = new Date(todayStart); ydayStart.setDate(ydayStart.getDate() - 1)
  const weekStart = new Date(todayStart); weekStart.setDate(weekStart.getDate() - 7)
  const groups = [
    { label: '今天', convs: [] },
    { label: '昨天', convs: [] },
    { label: '最近7天', convs: [] },
    { label: '更早', convs: [] },
  ]
  for (const c of conversations.value) {
    const t = c.updatedAt
    if (t >= todayStart.getTime()) groups[0].convs.push(c)
    else if (t >= ydayStart.getTime()) groups[1].convs.push(c)
    else if (t >= weekStart.getTime()) groups[2].convs.push(c)
    else groups[3].convs.push(c)
  }
  return groups.filter(g => g.convs.length > 0)
})

function loadConversations() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) conversations.value = JSON.parse(saved)
  } catch (e) {}

  if (conversations.value.length > 0) {
    const lastId = localStorage.getItem(STORAGE_KEY + ':current')
    const target = conversations.value.find(c => c.id === lastId) || conversations.value[0]
    currentConvId.value = target.id
    chatHistory.value = target.messages || []
  } else {
    createNewConversation()
  }
}

function saveConversations() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations.value))
    if (currentConvId.value) localStorage.setItem(STORAGE_KEY + ':current', currentConvId.value)
  } catch (e) {}
}

function updateCurrentConversation() {
  const idx = conversations.value.findIndex(c => c.id === currentConvId.value)
  if (idx === -1) return
  const conv = conversations.value[idx]
  conv.messages = JSON.parse(JSON.stringify(chatHistory.value))
  conv.updatedAt = Date.now()
  if (conv.title === '新对话') {
    const first = chatHistory.value.find(m => m.role === 'user')
    if (first) {
      const raw = first.fileName || first.content || '新对话'
      conv.title = raw.slice(0, 22) + (raw.length > 22 ? '...' : '')
    }
  }
  saveConversations()
}

function createNewConversation() {
  const id = `conv-${Date.now()}`
  conversations.value.unshift({ id, title: '新对话', messages: [], createdAt: Date.now(), updatedAt: Date.now() })
  currentConvId.value = id
  chatHistory.value = []
  saveConversations()
}

function switchConversation(id) {
  if (isProcessing.value || id === currentConvId.value) return
  updateCurrentConversation()
  const conv = conversations.value.find(c => c.id === id)
  if (!conv) return
  currentConvId.value = id
  chatHistory.value = conv.messages || []
  localStorage.setItem(STORAGE_KEY + ':current', id)
}

function deleteConversation(id) {
  const idx = conversations.value.findIndex(c => c.id === id)
  if (idx === -1) return
  conversations.value.splice(idx, 1)
  if (currentConvId.value === id) {
    conversations.value.length > 0 ? switchConversation(conversations.value[0].id) : createNewConversation()
  }
  saveConversations()
}

onMounted(loadConversations)
// keep-alive: save state when navigating away (deactivated) and on true destroy
onDeactivated(updateCurrentConversation)
onUnmounted(updateCurrentConversation)

/* ===== Examples ===== */
const examples = [
  '生成5道高中三角函数解答题，难度中等',
  '出3道数列极限的计算题',
  '参考上传图片，找10道相似题目',
]

/* ===== Node name mapping ===== */
const getNodeName = (node) => ({
  parse: '多模态意图与考点分析',
  retrieve: '内网私有库与互联网并发检索',
  review: 'LLM 深度逻辑推理与淘汰去噪',
  compile: '自动化 LaTeX 排版与 PDF 渲染',
}[node] || node)

/* ===== Scroll ===== */
const scrollToBottom = async () => {
  await nextTick()
  scrollAnchor.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}

/* ===== Auto-resize textarea ===== */
function autoResize() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

/* ===== Attachment handling ===== */
function attachFile(file) {
  imgFile.value = file
  attachedFileName.value = file.name
  if (file.type.startsWith('image/')) {
    const reader = new FileReader()
    reader.onload = (ev) => { imgPreview.value = ev.target.result }
    reader.readAsDataURL(file)
  } else {
    imgPreview.value = null
  }
}

function clearAttach() {
  imgFile.value = null
  imgPreview.value = null
  attachedFileName.value = ''
}

const handleImage = (e) => {
  const file = e.target.files[0]
  if (file) attachFile(file)
  e.target.value = ''
}

const handlePaste = (e) => {
  const items = [...(e.clipboardData?.items || [])]
  const fileItem = items.find(it => it.kind === 'file' && (it.type.startsWith('image/') || it.type === 'application/pdf'))
  if (fileItem) {
    const file = fileItem.getAsFile()
    if (file) { e.preventDefault(); attachFile(file) }
  }
}

/* ===== Download PDF ===== */
const downloadPDF = async (url, filename) => {
  try {
    const response = await fetch(url)
    const blob = await response.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(blobUrl)
  } catch (error) {
    console.error('下载文件失败:', error)
  }
}

/* ===== Send task ===== */
const sendTask = async () => {
  if (isProcessing.value || (!prompt.value && !imgFile.value)) return

  chatHistory.value.push({
    role: 'user',
    content: prompt.value,
    image: imgPreview.value,
    fileName: !imgPreview.value ? attachedFileName.value : '',
  })

  const agentIdx = chatHistory.value.push({
    role: 'agent', status: 'thinking', steps: [],
    pdf_student: '', pdf_teacher: '',
    download_name_student: '', download_name_teacher: '',
    error: null,
  }) - 1

  const currentMsg = chatHistory.value[agentIdx]
  const formData = new FormData()
  formData.append('prompt', prompt.value)
  if (imgFile.value) formData.append('reference_file', imgFile.value)

  isProcessing.value = true
  prompt.value = ''
  imgFile.value = null
  imgPreview.value = null
  attachedFileName.value = ''
  if (textareaEl.value) textareaEl.value.style.height = 'auto'
  scrollToBottom()

  try {
    const res = await fetch('http://localhost:8000/chat', { method: 'POST', body: formData })
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const lines = decoder.decode(value, { stream: true }).split('\n\n')
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6))
            if (data.node !== 'finish') currentMsg.steps.push(data)
            if (data.status === 'done' && data.node === 'finish') {
              currentMsg.status = 'done'
              currentMsg.pdf_student = data.pdf_student || ''
              currentMsg.pdf_teacher = data.pdf_teacher || ''
              currentMsg.download_name_student = data.download_name_student || '学生卷.pdf'
              currentMsg.download_name_teacher = data.download_name_teacher || '解析卷.pdf'
            }
            scrollToBottom()
          } catch (e) {
            console.warn('解析单条 JSON 流数据失败:', e, line)
          }
        }
      }
    }
  } catch (error) {
    console.error('请求发生错误:', error)
    currentMsg.status = 'error'
    currentMsg.error = '请求中断或后端无响应，请检查终端日志。'
  } finally {
    if (currentMsg.status === 'thinking') currentMsg.status = 'error'
    isProcessing.value = false
    scrollToBottom()
    updateCurrentConversation()
  }
}
</script>

<style scoped>
/* ===== Layout ===== */
.chat-layout {
  height: 100%;
  display: flex;
  overflow: hidden;
  background: var(--bg-deep);
}

/* ===== Sidebar ===== */
.sidebar {
  width: 288px;
  flex-shrink: 0;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-sub);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* New Conversation Button */
.new-conv-btn {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 16px 14px 10px;
  padding: 10px 16px;
  background: var(--violet-dim);
  border: 1px solid rgba(139,127,245,0.35);
  border-radius: 11px;
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 600;
  color: var(--violet-hi);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.new-conv-btn:hover {
  background: rgba(139,127,245,0.3);
  border-color: var(--violet);
}

/* Conversation List */
.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
  min-height: 0;
}

.conv-group-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 8px 8px 4px;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 9px;
  cursor: pointer;
  transition: background 0.12s;
  position: relative;
}

.conv-item:hover {
  background: var(--bg-elevated);
}

.conv-item.active {
  background: var(--violet-dim);
  border: 1px solid rgba(139,127,245,0.2);
}

.conv-item-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.conv-item.active .conv-item-icon {
  color: var(--violet-hi);
}

.conv-item-title {
  flex: 1;
  font-size: 14px;
  color: var(--text-sec);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.conv-item.active .conv-item-title {
  color: var(--violet-hi);
  font-weight: 500;
}

.conv-item-del {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 5px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.12s;
}

.conv-item:hover .conv-item-del { opacity: 1; }
.conv-item-del:hover { background: rgba(244,63,94,0.15); color: #f87171; }

.conv-empty {
  text-align: center;
  padding: 32px 16px;
  font-size: 13px;
  color: var(--text-muted);
}

/* ===== Chat Main ===== */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 28px 28px 0;
}

.messages-inner {
  max-width: 780px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding-bottom: 16px;
}

/* Welcome */
.welcome-screen {
  max-width: 520px;
  margin: 80px auto 0;
  text-align: center;
}

.welcome-icon {
  width: 66px;
  height: 66px;
  background: var(--violet-dim);
  border: 1px solid rgba(139,127,245,0.4);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--violet-hi);
  margin: 0 auto 22px;
}

.welcome-title {
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 700;
  color: var(--text-bright);
  margin: 0 0 8px;
}

.welcome-sub {
  font-size: 15px;
  color: var(--text-sec);
  margin: 0 0 28px;
}

.welcome-examples {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.example-btn {
  padding: 11px 16px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-family: var(--font-ui);
  font-size: 14px;
  color: var(--text-sec);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}

.example-btn:hover {
  border-color: var(--violet);
  color: var(--violet-hi);
  background: var(--violet-glow);
}

/* User Bubble */
.msg-user {
  display: flex;
  justify-content: flex-end;
}

.bubble-user {
  background: var(--violet-dim);
  border: 1px solid rgba(139,127,245,0.3);
  border-radius: 18px 18px 4px 18px;
  padding: 12px 18px;
  max-width: 75%;
}

.bubble-image {
  border-radius: 8px;
  max-height: 160px;
  margin-bottom: 8px;
  object-fit: contain;
  border: 1px solid var(--border);
  display: block;
}

.bubble-file-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: rgba(139,127,245,0.15);
  border: 1px solid rgba(139,127,245,0.3);
  border-radius: 8px;
  padding: 6px 12px;
  margin-bottom: 7px;
  font-size: 13px;
  color: var(--violet-hi);
  max-width: 100%;
}

.bubble-file-badge span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bubble-text {
  font-size: 16px;
  color: var(--text-bright);
  white-space: pre-wrap;
  margin: 0;
  line-height: 1.65;
}

/* Agent Message */
.msg-agent {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--violet-hi);
  flex-shrink: 0;
  margin-top: 2px;
}

.agent-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Reasoning Block */
.reasoning-block {
  background: var(--bg-elevated);
  border: 1px solid var(--border-sub);
  border-radius: 12px;
  overflow: hidden;
}

.reasoning-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 13px 16px;
  cursor: pointer;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-sec);
  list-style: none;
  user-select: none;
  transition: color 0.15s;
}

.reasoning-summary:hover { color: var(--text-pri); }
.sparkle-icon { color: var(--violet-hi); }
.chevron { margin-left: auto; transition: transform 0.2s; }
details[open] .chevron { transform: rotate(180deg); }

.reasoning-steps {
  border-top: 1px solid var(--border-sub);
  padding: 16px 16px 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.step-item {
  display: flex;
  gap: 12px;
  position: relative;
}

.step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--violet-hi);
  border: 2px solid var(--bg-elevated);
  flex-shrink: 0;
  margin-top: 6px;
}

.step-body { flex: 1; min-width: 0; }

.step-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-pri);
  margin: 0 0 4px;
}

.step-detail { font-size: 14px; color: var(--text-sec); }

.reasoning-empty {
  border-top: 1px solid var(--border-sub);
  padding: 12px 16px;
  font-size: 14px;
  color: var(--text-muted);
}

/* PDF Card */
.pdf-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
}

.pdf-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-pri);
  margin-bottom: 12px;
}

.pdf-ok-icon { color: var(--green); }

.pdf-btns { display: flex; flex-wrap: wrap; gap: 10px; }

.pdf-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 20px;
  border-radius: 9px;
  font-family: var(--font-ui);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.pdf-btn.primary {
  background: var(--violet-dim);
  border-color: rgba(139,127,245,0.4);
  color: var(--violet-hi);
}

.pdf-btn.primary:hover {
  background: rgba(139,127,245,0.3);
  border-color: var(--violet);
}

.pdf-btn.secondary {
  background: var(--bg-card);
  border-color: var(--border);
  color: var(--text-sec);
}

.pdf-btn.secondary:hover {
  border-color: var(--border-hi);
  color: var(--text-pri);
}

/* Error */
.error-block {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(244,63,94,0.08);
  border: 1px solid rgba(244,63,94,0.2);
  border-radius: 10px;
  padding: 13px 16px;
  font-size: 15px;
  color: #f87171;
}

.scroll-anchor { height: 16px; }

/* ===== Input Bar ===== */
.input-bar {
  flex-shrink: 0;
  background: var(--bg-surface);
  border-top: 1px solid var(--border-sub);
  padding: 16px 24px 12px;
}

/* Attachment preview */
.attachment-row {
  max-width: 780px;
  margin: 0 auto 10px;
  display: flex;
  align-items: center;
}

.preview-wrap {
  display: inline-flex;
  position: relative;
}

.preview-img {
  height: 66px;
  border-radius: 8px;
  border: 1px solid var(--border);
  object-fit: contain;
}

.file-badge-wrap {
  display: inline-flex;
  align-items: center;
  position: relative;
  gap: 8px;
}

.file-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-hi);
  border-radius: 10px;
  padding: 8px 14px 8px 12px;
  max-width: 280px;
}

.file-badge-icon { color: var(--violet-hi); flex-shrink: 0; }

.file-badge-name {
  font-size: 14px;
  color: var(--text-pri);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.file-badge-ext {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--amber);
  background: rgba(212,164,74,0.12);
  border: 1px solid rgba(212,164,74,0.25);
  border-radius: 4px;
  padding: 1px 6px;
  flex-shrink: 0;
}

.preview-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ef4444;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

/* Input row */
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  max-width: 780px;
  margin: 0 auto;
}

.attach-btn {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-sec);
  cursor: pointer;
  transition: all 0.15s;
}

.attach-btn:hover {
  border-color: var(--violet);
  color: var(--violet-hi);
}

.hidden-input { display: none; }

.chat-input {
  flex: 1;
  min-height: 44px;
  max-height: 200px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 11px 16px;
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--text-pri);
  outline: none;
  resize: none;
  line-height: 1.6;
  transition: border-color 0.18s, box-shadow 0.18s;
}

.chat-input::placeholder { color: var(--text-muted); }

.chat-input:focus {
  border-color: var(--violet);
  box-shadow: 0 0 0 3px var(--violet-glow);
}

.send-btn {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  background: var(--violet-dim);
  border: 1px solid rgba(139,127,245,0.4);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--violet-hi);
  cursor: pointer;
  transition: all 0.15s;
}

.send-btn:hover:not(:disabled) {
  background: rgba(139,127,245,0.4);
  border-color: var(--violet);
  color: var(--text-bright);
}

.send-btn.processing {
  background: rgba(212,164,74,0.15);
  border-color: rgba(212,164,74,0.4);
  color: var(--amber);
}

.send-btn:disabled:not(.processing) { opacity: 0.3; cursor: not-allowed; }

.input-hint {
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
  margin: 8px 0 0;
}

/* ===== Utilities ===== */
.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
