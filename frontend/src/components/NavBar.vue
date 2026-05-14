<template>
  <nav class="navbar">
    <div class="navbar-inner">
      <!-- Brand -->
      <RouterLink to="/" class="brand">
        <div class="brand-icon">
          <BookOpen :size="16" stroke-width="2.2" />
        </div>
        <span class="brand-name">YT 教研</span>
        <span class="brand-sep">|</span>
        <span class="brand-sub">数学可视化实验室</span>
      </RouterLink>

      <!-- Center Tabs -->
      <div class="nav-tabs">
        <RouterLink to="/" class="nav-tab" :class="{ active: route.path === '/' }">
          <Library :size="15" />
          <span>动画资源库</span>
        </RouterLink>
        <RouterLink to="/chat" class="nav-tab" :class="{ active: route.path === '/chat' }">
          <BrainCircuit :size="15" />
          <span>AI 出题助手</span>
        </RouterLink>
        <RouterLink to="/knowledge" class="nav-tab" :class="{ active: route.path === '/knowledge' }">
          <Database :size="15" />
          <span>知识库管理</span>
        </RouterLink>
      </div>

      <!-- Right -->
      <div class="nav-right">
        <span class="version-badge">Beta</span>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { BookOpen, Library, BrainCircuit, Database } from 'lucide-vue-next'

const route = useRoute()
</script>

<style scoped>
.navbar {
  height: 58px;
  flex-shrink: 0;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-sub);
  position: relative;
  z-index: 100;
}

.navbar-inner {
  height: 100%;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  align-items: center;
  gap: 0;
}

/* Brand */
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  flex-shrink: 0;
}

.brand-icon {
  width: 30px;
  height: 30px;
  background: var(--violet-dim);
  border: 1px solid var(--violet);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--violet-hi);
}

.brand-name {
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 600;
  color: var(--text-bright);
  letter-spacing: 0.02em;
}

.brand-sep {
  color: var(--border-hi);
  font-size: 16px;
  margin: 0 4px;
}

.brand-sub {
  font-size: 14px;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}

/* Nav Tabs */
.nav-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 auto;
  background: var(--bg-elevated);
  border: 1px solid var(--border-sub);
  border-radius: 10px;
  padding: 4px;
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 16px;
  border-radius: 7px;
  text-decoration: none;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-sec);
  transition: all 0.18s ease;
  white-space: nowrap;
}

.nav-tab:hover {
  color: var(--text-pri);
  background: var(--bg-card);
}

.nav-tab.active {
  color: var(--violet-hi);
  background: var(--violet-dim);
  border: 1px solid rgba(139,127,245,0.3);
}

/* Right Side */
.nav-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.version-badge {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--amber);
  background: rgba(212,164,74,0.1);
  border: 1px solid rgba(212,164,74,0.25);
  border-radius: 5px;
  padding: 3px 8px;
}
</style>
