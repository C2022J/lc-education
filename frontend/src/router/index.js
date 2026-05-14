import { createRouter, createWebHistory } from 'vue-router'
import AnimationLibrary from '../views/AnimationLibrary.vue'
import ChatView from '../views/ChatView.vue'
import KnowledgeBase from '../views/KnowledgeBase.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: AnimationLibrary, meta: { title: '动画资源库' } },
    { path: '/chat', component: ChatView, meta: { title: 'AI 出题助手' } },
    { path: '/knowledge', component: KnowledgeBase, meta: { title: '知识库管理' } },
  ],
})
