<!-- src/components/Markdown.vue -->
<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps({
  content: { type: String, default: '' }
})

// 开启 GFM (GitHub Flavored Markdown) 支持表格等
marked.setOptions({ gfm: true, breaks: true })

const html = computed(() => {
  if (!props.content) return ''
  // 将 Markdown 转为 HTML 后，强制洗毒
  return DOMPurify.sanitize(marked.parse(props.content))
})
</script>

<template>
  <!-- 在 style 中定义 .markdown-content 的样式 -->
  <div class="markdown-content" v-html="html"></div>
</template>

<style>
.markdown-content p { margin: 0.4em 0; line-height: 1.6; }
.markdown-content pre { background: #1a1a26; border: 1px solid #26263a; padding: 0.6rem; border-radius: 0.5rem; overflow-x: auto; }
.markdown-content code { background: #1e1e2c; color: #c4b5fd; padding: 0.1rem 0.4rem; border-radius: 0.3rem; font-family: 'JetBrains Mono', monospace; font-size: 0.85em; }
.markdown-content strong { color: #e2e2f0; }
.markdown-content ul, .markdown-content ol { padding-left: 1.4em; margin: 0.4em 0; }
.markdown-content li { margin: 0.2em 0; }
</style>