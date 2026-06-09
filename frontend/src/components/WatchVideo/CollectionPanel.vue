<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import type { Video } from '@/types/media'

const props = defineProps<{
  currentVideoId: number
  currentVideoFilename: string
}>()

const videos = ref<Video[]>([])
const loading = ref(false)

onMounted(() => {
  // Collection feature removed - always show empty state
  loading.value = false
  videos.value = []
})

watch(() => props.currentVideoId, () => {
  // Collection feature removed - always show empty state
  loading.value = false
  videos.value = []
})
</script>

<template>
  <div class="collection-panel">
    <!-- No Collection State -->
    <div class="text-slate-500 dark:text-slate-400 text-center py-8">
      <div class="text-sm">此视频不属于任何集合</div>
    </div>
  </div>
</template>

<style scoped>
/* Custom scrollbar for the videos list */
.overflow-y-auto::-webkit-scrollbar {
  width: 4px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.8);
  border-radius: 2px;
}

:global(html.dark) .overflow-y-auto::-webkit-scrollbar-track {
  background: rgba(71, 85, 105, 0.3);
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.45);
  border-radius: 2px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: rgba(100, 116, 139, 0.65);
}

:global(html.dark) .overflow-y-auto::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.5);
}

:global(html.dark) .overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.7);
}
</style>
