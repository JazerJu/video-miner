<!-- src/components/Home/BatchToolbar.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import { FolderOutput, Sparkles, Trash2, X } from 'lucide-vue-next'

const nothingSelected = computed(() => !props.selectedIds.length)

/* --- props ------------------------------------------------- */
const props = defineProps<{
  batchMode: boolean
  selectedIds: number[]
}>()

/* --- emits ------------------------------------------------- */
const emit = defineEmits<{
  (e: 'update:batchMode', v: boolean): void
  (e: 'show-move-dialog'): void
  (e: 'generate-subtitles'): void
  (e: 'delete-videos'): void
  (e: 'deselect-all'): void
}>()
</script>

<template>
  <div class="flex items-center gap-2">
    <template v-if="props.batchMode">
      <el-tooltip content="移动分类" placement="top">
        <button
          :disabled="nothingSelected"
          class="batch-icon-btn"
          @click="emit('show-move-dialog')"
        >
          <FolderOutput :size="18" />
        </button>
      </el-tooltip>

      <el-tooltip content="生成字幕" placement="top">
        <button
          :disabled="nothingSelected"
          class="batch-icon-btn"
          @click="emit('generate-subtitles')"
        >
          <Sparkles :size="18" />
        </button>
      </el-tooltip>

      <el-tooltip content="删除视频" placement="top">
        <button
          :disabled="nothingSelected"
          class="batch-icon-btn batch-icon-btn--danger"
          @click="emit('delete-videos')"
        >
          <Trash2 :size="18" />
        </button>
      </el-tooltip>

      <div class="mx-1 h-5 w-px bg-white/15"></div>

      <el-tooltip content="取消选择" placement="top">
        <button
          class="batch-icon-btn batch-icon-btn--cancel"
          @click="emit('deselect-all')"
        >
          <X :size="18" />
        </button>
      </el-tooltip>
    </template>
  </div>
</template>

<style scoped>
.batch-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(24, 40, 77, 0.6);
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  transition: all 0.2s ease;
}

.batch-icon-btn:hover:not(:disabled) {
  background: rgba(24, 40, 77, 0.9);
  border-color: rgba(96, 165, 250, 0.5);
  color: rgb(96, 165, 250);
}

.batch-icon-btn--danger:hover:not(:disabled) {
  border-color: rgba(239, 68, 68, 0.5);
  color: rgb(239, 68, 68);
}

.batch-icon-btn--cancel:hover:not(:disabled) {
  border-color: rgba(148, 163, 184, 0.5);
  color: rgb(148, 163, 184);
}

.batch-icon-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
</style>
