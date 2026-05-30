<script setup lang="ts">
import { useProgress } from '@/composables/useProgress'

const { progress, visible } = useProgress()
</script>

<template>
  <div v-if="visible" class="top-progress">
    <div
      class="progress-bar"
      :style="{ width: `${progress}%` }"
    />
  </div>
</template>

<style scoped>
.top-progress {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  z-index: 9999;
  pointer-events: none;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #34d399, #6ee7b7);
  transition: width 0.2s ease-out;
  box-shadow: 0 0 10px rgba(16, 185, 129, 0.7);
}
</style>
