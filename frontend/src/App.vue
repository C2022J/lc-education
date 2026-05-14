<template>
  <div class="app-shell">
    <NavBar />
    <div class="view-container">
      <RouterView v-slot="{ Component }">
        <keep-alive :include="['ChatView']">
          <component :is="Component" />
        </keep-alive>
      </RouterView>
    </div>
  </div>
</template>

<script setup>
import NavBar from './components/NavBar.vue'
</script>

<style scoped>
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-deep);
  overflow: hidden;
}
.view-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
