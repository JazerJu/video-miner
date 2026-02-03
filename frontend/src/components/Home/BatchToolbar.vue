<!-- src/components/Home/BatchToolbar.vue -->
<script setup lang="ts">
import { defineProps, defineEmits, computed } from 'vue'

const nothingSelected = computed(() => !props.selectedIds.length)

/* ─── props ───────────────────────────────────────────── */
const props = defineProps<{
  batchMode: boolean
  selectedIds: number[]
}>()

/* ─── emits ───────────────────────────────────────────── */
const emit = defineEmits<{
  (e: 'update:batchMode', v: boolean): void
  (e: 'show-move-dialog'): void
  (e: 'generate-subtitles'): void
  (e: 'delete-videos'): void
  (e: 'concat-videos'): void
}>()
</script>

<template>
  <div class="flex flex-wrap items-center gap-3 mb-4">
    <!-- 只有批量模式下才显示下面三颗按钮 -->
    <template v-if="props.batchMode">
      <el-button
        size="default"
        type="primary"
        :disabled="nothingSelected"
        @click="emit('show-move-dialog')"
        class="batch-button"
      >
        移动分类
      </el-button>



      <el-button
        size="default"
        type="success"
        :disabled="nothingSelected"
        @click="emit('generate-subtitles')"
        class="batch-button"
      >
        生成字幕
      </el-button>

      <el-button
        size="default"
        type="danger"
        :disabled="nothingSelected"
        @click="emit('delete-videos')"
        class="batch-button"
      >
        删除视频
      </el-button>

      <el-button
        size="default"
        type="warning"
        :disabled="nothingSelected"
        @click="emit('concat-videos')"
        class="batch-button"
      >
        合并视频
      </el-button>

    </template>
  </div>
</template>

<style scoped>
.batch-button {
  font-size: 1.2rem !important;
  font-weight: 500 !important;
  padding: 16px 32px !important;
  height: auto !important;
  border-radius: 12px !important;
  background: rgba(24, 40, 77, 0.8) !important;
  backdrop-filter: blur(10px);
  transition: all 0.3s ease !important;
  border: 1px solid rgba(24, 40, 77, 0.9) !important;
}

/* 不同按钮的文字颜色 */
.batch-button:nth-child(1) {
  color: rgb(70, 139, 226) !important;
}

.batch-button:nth-child(2) {
  color: rgb(46, 152, 151) !important;
}

.batch-button:nth-child(3) {
  color: rgb(204, 100, 100) !important;
}

/* 合并视频按钮颜色 */
.batch-button:nth-child(4) {
  color: rgb(242, 178, 49) !important;
}

/* 悬停效果 */
.batch-button:hover {
  transform: translateY(-2px) !important;
  backdrop-filter: blur(15px) !important;
  background: rgba(24, 40, 77, 0.9) !important;
  box-shadow: 0 8px 25px rgba(24, 40, 77, 0.3) !important;
}

/* 禁用状态 */
.batch-button.is-disabled {
  background: rgba(24, 40, 77, 0.4) !important;
  border: 1px solid rgba(24, 40, 77, 0.5) !important;
  color: rgba(255, 255, 255, 0.4) !important;
  transform: none !important;
  box-shadow: none !important;
  backdrop-filter: blur(5px) !important;
}
</style>
