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
/* 简单的排版美化 */
.markdown-content p { margin: 0.5em 0; }
.markdown-content pre { background: #f3f4f6; padding: 0.5rem; border-radius: 0.5rem; overflow-x: auto; }
.markdown-content code { background: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 0.25rem; font-family: monospace; }
</style>