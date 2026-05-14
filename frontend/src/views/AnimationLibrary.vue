<template>
  <div class="library">
    <!-- Page Hero -->
    <div class="hero">
      <div class="hero-inner">
        <div class="hero-label">
          <Sparkles :size="12" />
          <span>可视化资源库</span>
        </div>
        <h1 class="hero-title">探索数学的<em>动态之美</em></h1>
        <p class="hero-desc">交互式动画，让抽象概念变得直观可感</p>

        <!-- Search -->
        <div class="search-box">
          <Search :size="17" class="search-ico" />
          <input
            v-model="searchQuery"
            class="search-input"
            placeholder="搜索动画标题、标签或描述..."
            type="text"
          />
          <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">
            <X :size="14" />
          </button>
        </div>
      </div>
    </div>

    <!-- Filter Chips -->
    <div class="filters-wrap">
      <div class="filters">
        <button
          v-for="cat in categories"
          :key="cat"
          class="filter-chip"
          :class="{ active: activeCategory === cat }"
          @click="toggleCategory(cat)"
        >
          {{ cat }}
        </button>
      </div>
      <span class="results-count">{{ filteredAnimations.length }} 个动画</span>
    </div>

    <!-- Grid -->
    <div class="grid-area">
      <div
        v-if="filteredAnimations.length > 0"
        class="anim-grid"
      >
        <article
          v-for="(anim, i) in filteredAnimations"
          :key="anim.id"
          class="anim-card"
          :style="{ '--c': anim.color, '--delay': `${i * 60}ms` }"
          @click="openViewer(anim)"
          tabindex="0"
          @keydown.enter="openViewer(anim)"
        >
          <!-- Card Banner -->
          <div class="card-banner">
            <div class="banner-glow"></div>
            <div class="banner-pattern"></div>
            <div class="banner-symbol">
              <!-- Inline SVG preview per animation type -->
              <component :is="anim.previewComponent" />
            </div>
            <div class="play-hint">
              <ExternalLink :size="13" />
              <span>新标签页打开</span>
            </div>
          </div>

          <!-- Card Body -->
          <div class="card-body">
            <div class="card-tags">
              <span v-for="tag in anim.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
            </div>
            <h3 class="card-title">{{ anim.title }}</h3>
            <p class="card-desc">{{ anim.description }}</p>
            <div class="card-footer">
              <span class="card-subject">{{ anim.subject }}</span>
              <span class="card-open">
                查看
                <ArrowRight :size="13" />
              </span>
            </div>
          </div>
        </article>
      </div>

      <!-- Empty State -->
      <div v-else class="empty-state">
        <div class="empty-icon">🔭</div>
        <p class="empty-text">没有找到匹配的动画</p>
        <button class="empty-reset" @click="searchQuery = ''; activeCategory = '全部'">
          清除筛选条件
        </button>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, h } from 'vue'
import { Search, X, ExternalLink, ArrowRight, Sparkles } from 'lucide-vue-next'



/* ---------- SVG Preview Components ---------- */
const SinePreview = {
  render() {
    return h('svg', { viewBox: '0 0 200 100', fill: 'none', xmlns: 'http://www.w3.org/2000/svg', style: 'width:100%;height:100%' }, [
      // Unit circle
      h('circle', { cx: '50', cy: '50', r: '32', stroke: 'rgba(139,127,245,0.5)', 'stroke-width': '1.5' }),
      h('line', { x1: '50', y1: '18', x2: '50', y2: '82', stroke: 'rgba(255,255,255,0.15)', 'stroke-width': '1' }),
      h('line', { x1: '18', y1: '50', x2: '82', y2: '50', stroke: 'rgba(255,255,255,0.15)', 'stroke-width': '1' }),
      // Radius line to π/4
      h('line', { x1: '50', y1: '50', x2: '73', y2: '27', stroke: 'rgba(139,127,245,0.9)', 'stroke-width': '2', 'stroke-linecap': 'round' }),
      // sin projection (green)
      h('line', { x1: '73', y1: '27', x2: '73', y2: '50', stroke: 'rgba(74,222,128,0.8)', 'stroke-width': '1.5', 'stroke-dasharray': '3,2' }),
      // cos projection (amber)
      h('line', { x1: '50', y1: '50', x2: '73', y2: '50', stroke: 'rgba(251,191,36,0.8)', 'stroke-width': '1.5', 'stroke-dasharray': '3,2' }),
      // Point on circle
      h('circle', { cx: '73', cy: '27', r: '4', fill: '#8b7ff5' }),
      // Sine wave on right panel
      h('path', {
        d: 'M 90 50 C 100 50, 103 20, 113 20 C 123 20, 127 80, 137 80 C 147 80, 150 50, 160 50 C 170 50, 173 20, 183 20 C 193 20, 197 80, 207 80',
        stroke: 'rgba(74,222,128,0.9)', 'stroke-width': '2', 'stroke-linecap': 'round', fill: 'none'
      }),
      // Cosine wave on right panel (offset)
      h('path', {
        d: 'M 90 20 C 100 20, 103 50, 113 50 C 123 50, 127 80, 137 80 C 147 80, 150 50, 160 50 C 170 50, 173 20, 183 20',
        stroke: 'rgba(251,191,36,0.7)', 'stroke-width': '1.5', 'stroke-linecap': 'round', fill: 'none',
        'stroke-dasharray': '4,3'
      }),
      // Connecting bridge line
      h('line', { x1: '73', y1: '27', x2: '113', y2: '20', stroke: 'rgba(139,127,245,0.35)', 'stroke-width': '1', 'stroke-dasharray': '3,3' }),
      // Labels
      h('text', { x: '105', y: '14', fill: 'rgba(74,222,128,0.9)', 'font-size': '8', 'font-family': 'JetBrains Mono' }, 'sin θ'),
      h('text', { x: '105', y: '93', fill: 'rgba(251,191,36,0.9)', 'font-size': '8', 'font-family': 'JetBrains Mono' }, 'cos θ'),
    ])
  }
}

/* ---------- Animation Data ---------- */
const animations = [
  {
    id: 'sine-animation',
    title: '正弦与余弦的几何意义',
    subject: '高中数学',
    tags: ['三角函数', '单位圆', '函数图像'],
    description: '通过可拖拽的单位圆，动态演示 sin(θ) 和 cos(θ) 的几何定义与函数图像的实时联系。',
    path: '/animations/sine-animation.html',
    color: '#8b7ff5',
    previewComponent: SinePreview,
  },
]

/* ---------- State ---------- */
const allTags = [...new Set(animations.flatMap(a => a.tags))]
const categories = ['全部', ...allTags]

const searchQuery = ref('')
const activeCategory = ref('全部')
const activeAnim = ref(null)

const filteredAnimations = computed(() => {
  let result = animations
  if (activeCategory.value !== '全部') {
    result = result.filter(a => a.tags.includes(activeCategory.value))
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    result = result.filter(a =>
      a.title.includes(q) ||
      a.description.includes(q) ||
      a.tags.some(t => t.includes(q))
    )
  }
  return result
})

function toggleCategory(cat) {
  activeCategory.value = (activeCategory.value === cat && cat !== '全部') ? '全部' : cat
}

function openViewer(anim) {
  window.open(anim.path, '_blank')
}
</script>

<style scoped>
/* ===== Page Layout ===== */
.library {
  height: 100%;
  overflow-y: auto;
  background: var(--bg-deep);
}

/* ===== Hero ===== */
.hero {
  background: linear-gradient(180deg, var(--bg-surface) 0%, var(--bg-deep) 100%);
  border-bottom: 1px solid var(--border-sub);
  padding: 52px 0 36px;
}

.hero-inner {
  max-width: 760px;
  margin: 0 auto;
  padding: 0 24px;
  text-align: center;
}

.hero-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--violet-hi);
  background: var(--violet-glow);
  border: 1px solid rgba(139,127,245,0.25);
  border-radius: 20px;
  padding: 5px 14px;
  margin-bottom: 20px;
}

.hero-title {
  font-family: var(--font-serif);
  font-size: clamp(30px, 4vw, 44px);
  font-weight: 700;
  color: var(--text-bright);
  line-height: 1.25;
  margin: 0 0 12px;
  letter-spacing: -0.02em;
}

.hero-title em {
  font-style: normal;
  background: linear-gradient(135deg, var(--violet-hi) 0%, #c4b5fd 50%, var(--teal) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-desc {
  font-size: 16px;
  color: var(--text-sec);
  margin: 0 0 32px;
}

/* Search */
.search-box {
  position: relative;
  max-width: 540px;
  margin: 0 auto;
}

.search-ico {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  height: 48px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0 48px 0 46px;
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--text-pri);
  outline: none;
  transition: border-color 0.18s, box-shadow 0.18s;
}

.search-input::placeholder { color: var(--text-muted); }

.search-input:focus {
  border-color: var(--violet);
  box-shadow: 0 0 0 3px var(--violet-glow);
}

.search-clear {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px;
  color: var(--text-sec);
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: all 0.15s;
}

.search-clear:hover {
  color: var(--text-bright);
  background: var(--border);
}

/* ===== Filters ===== */
.filters-wrap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 24px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-chip {
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  color: var(--text-sec);
}

.filter-chip:hover {
  border-color: var(--border-hi);
  color: var(--text-pri);
}

.filter-chip.active {
  background: var(--violet-dim);
  border-color: rgba(139,127,245,0.4);
  color: var(--violet-hi);
}

.results-count {
  font-size: 14px;
  color: var(--text-muted);
  white-space: nowrap;
}

/* ===== Grid ===== */
.grid-area {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 24px 60px;
}

.anim-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

/* ===== Cards ===== */
.anim-card {
  background: var(--bg-card);
  border: 1px solid var(--border-sub);
  border-radius: 16px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1),
              box-shadow 0.22s ease,
              border-color 0.2s ease;
  animation: fadeIn 0.4s ease-out both;
  animation-delay: var(--delay, 0ms);
}

.anim-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 16px 48px rgba(0,0,0,0.5), 0 0 0 1px var(--c, #8b7ff5), 0 0 24px rgba(139,127,245,0.12);
  border-color: var(--c, #8b7ff5);
}

.anim-card:focus-visible {
  outline: 2px solid var(--violet);
  outline-offset: 2px;
}

/* Card Banner */
.card-banner {
  position: relative;
  height: 160px;
  overflow: hidden;
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--c, #8b7ff5) 25%, #0d0d18),
    color-mix(in srgb, var(--c, #8b7ff5) 12%, #09090f)
  );
}

.banner-glow {
  position: absolute;
  top: -40%;
  left: 50%;
  transform: translateX(-50%);
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, color-mix(in srgb, var(--c, #8b7ff5) 30%, transparent) 0%, transparent 70%);
  pointer-events: none;
}

.banner-pattern {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 24px 24px;
}

.banner-symbol {
  position: absolute;
  inset: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.play-hint {
  position: absolute;
  bottom: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--c, #8b7ff5);
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 20px;
  padding: 4px 10px;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.18s, transform 0.18s;
}

.anim-card:hover .play-hint {
  opacity: 1;
  transform: translateY(0);
}

/* Card Body */
.card-body {
  padding: 18px 20px 20px;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.tag {
  font-size: 12px;
  font-weight: 500;
  padding: 3px 9px;
  border-radius: 20px;
  background: rgba(139,127,245,0.12);
  color: var(--violet-hi);
  border: 1px solid rgba(139,127,245,0.2);
  letter-spacing: 0.01em;
}

.card-title {
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 600;
  color: var(--text-bright);
  margin: 0 0 8px;
  line-height: 1.4;
}

.card-desc {
  font-size: 14px;
  color: var(--text-sec);
  line-height: 1.6;
  margin: 0 0 16px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-subject {
  font-size: 13px;
  color: var(--text-muted);
}

.card-open {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--violet-hi);
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 0.18s, transform 0.18s;
}

.anim-card:hover .card-open {
  opacity: 1;
  transform: translateX(0);
}

/* ===== Empty State ===== */
.empty-state {
  text-align: center;
  padding: 80px 24px;
}

.empty-icon { font-size: 48px; margin-bottom: 16px; }
.empty-text { font-size: 17px; color: var(--text-sec); margin: 0 0 20px; }

.empty-reset {
  padding: 10px 22px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--text-pri);
  cursor: pointer;
  transition: all 0.15s;
}

.empty-reset:hover {
  border-color: var(--violet);
  color: var(--violet-hi);
}

</style>
