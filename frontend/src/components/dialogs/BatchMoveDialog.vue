<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from '@/composables/useNotification'
import axios from 'axios'

import { BACKEND } from '@/composables/ConfigAPI'

const props = defineProps<{
  modelValue: boolean
  selectedIds: number[]
  categories: { id: number | null; name: string }[] // ← 允许 null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'moved'): void // 通知父组件刷新
}>()

const targetId = ref<number | null>(null)

async function confirm() {
  if (targetId.value === null) {
    ElMessage.warning('请选择目标分类')
    return
  }
  // 并发调用接口，全部成功才算成功
  try {
    await Promise.all(
      props.selectedIds.map((id) =>
        axios.post(
          `${BACKEND}/api/videos/${id}/move_category`,
          { categoryId: targetId.value },
          { headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    ElMessage.success(`已移动 ${props.selectedIds.length} 个视频`)
    emit('moved')
    emit('update:modelValue', false)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '批量移动失败')
  }
}
</script>

<template>
  <el-dialog
    title="批量移动到分类"
    width="380px"
    class="batch-move-dialog-shell"
    :model-value="modelValue"
    @update:modelValue="emit('update:modelValue', $event)"
  >
    <div class="space-y-4 rounded-[20px] border border-slate-200 bg-slate-50 p-4 dark:border-white/8 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.84),rgba(17,24,39,0.78))]">
      <div>
        <label class="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-200">目标分类</label>
        <el-select
          v-model="targetId"
          placeholder="请选择目标分类"
          class="w-full"
          popper-class="batch-move-select-popper"
        >
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-3">
        <button
          class="inline-flex h-10 items-center justify-center rounded-xl border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 dark:border-white/12 dark:bg-white/[0.04] dark:text-slate-200 dark:hover:border-white/20 dark:hover:bg-white/[0.08]"
          @click="emit('update:modelValue', false)"
        >
          取消
        </button>
        <button
          class="inline-flex h-10 items-center justify-center rounded-xl border border-cyan-400/20 bg-[linear-gradient(135deg,rgba(34,211,238,0.24),rgba(59,130,246,0.24))] px-4 text-sm font-semibold text-cyan-700 transition hover:border-cyan-300/35 hover:shadow-[0_12px_28px_rgba(34,211,238,0.16)] dark:text-cyan-50"
          @click="confirm"
        >
          确定
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style>
.el-dialog.batch-move-dialog-shell,
.batch-move-dialog-shell .el-dialog {
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 22px;
  background: #ffffff;
  box-shadow: 0 24px 56px rgba(0, 0, 0, 0.12);
}

html.dark .el-dialog.batch-move-dialog-shell,
html.dark .batch-move-dialog-shell .el-dialog {
  border: 1px solid rgba(125, 211, 252, 0.1);
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.07), transparent 38%),
    linear-gradient(180deg, #111827, #0f172a 52%, #020617);
  box-shadow: 0 24px 56px rgba(2, 6, 23, 0.44);
}

.el-dialog.batch-move-dialog-shell .el-dialog__header,
.el-dialog.batch-move-dialog-shell .el-dialog__body,
.el-dialog.batch-move-dialog-shell .el-dialog__footer,
.batch-move-dialog-shell .el-dialog__header,
.batch-move-dialog-shell .el-dialog__body,
.batch-move-dialog-shell .el-dialog__footer {
  background: transparent;
}

.el-dialog.batch-move-dialog-shell .el-dialog__header,
.batch-move-dialog-shell .el-dialog__header {
  margin: 0;
  padding: 18px 18px 6px;
}

.el-dialog.batch-move-dialog-shell .el-dialog__title,
.batch-move-dialog-shell .el-dialog__title {
  color: #1e293b;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

html.dark .el-dialog.batch-move-dialog-shell .el-dialog__title,
html.dark .batch-move-dialog-shell .el-dialog__title {
  color: #f8fafc;
}

.el-dialog.batch-move-dialog-shell .el-dialog__headerbtn .el-dialog__close,
.batch-move-dialog-shell .el-dialog__headerbtn .el-dialog__close {
  color: #64748b;
}

html.dark .el-dialog.batch-move-dialog-shell .el-dialog__headerbtn .el-dialog__close,
html.dark .batch-move-dialog-shell .el-dialog__headerbtn .el-dialog__close {
  color: rgba(226, 232, 240, 0.78);
}

.el-dialog.batch-move-dialog-shell .el-dialog__body,
.batch-move-dialog-shell .el-dialog__body {
  padding: 10px 18px 14px;
}

.el-dialog.batch-move-dialog-shell .el-dialog__footer,
.batch-move-dialog-shell .el-dialog__footer {
  padding: 0 18px 18px;
}

.el-dialog.batch-move-dialog-shell .el-select__wrapper,
.batch-move-dialog-shell .el-select__wrapper {
  border: 1px solid #cbd5e1;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: inset 0 1px 0 rgba(15, 23, 42, 0.03);
}

html.dark .el-dialog.batch-move-dialog-shell .el-select__wrapper,
html.dark .batch-move-dialog-shell .el-select__wrapper {
  border: 1px solid rgba(125, 211, 252, 0.12);
  background: rgba(15, 23, 42, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.el-dialog.batch-move-dialog-shell .el-select__wrapper.is-focused,
.batch-move-dialog-shell .el-select__wrapper.is-focused {
  box-shadow: 0 0 0 1px rgba(103, 232, 249, 0.28);
  border-color: rgba(103, 232, 249, 0.28);
}

.el-dialog.batch-move-dialog-shell .el-select__placeholder,
.el-dialog.batch-move-dialog-shell .el-select__selected-item,
.batch-move-dialog-shell .el-select__placeholder,
.batch-move-dialog-shell .el-select__selected-item {
  color: #1e293b;
}

html.dark .el-dialog.batch-move-dialog-shell .el-select__placeholder,
html.dark .el-dialog.batch-move-dialog-shell .el-select__selected-item,
html.dark .batch-move-dialog-shell .el-select__placeholder,
html.dark .batch-move-dialog-shell .el-select__selected-item {
  color: #e2e8f0;
}

.el-dialog.batch-move-dialog-shell .el-select__caret,
.batch-move-dialog-shell .el-select__caret {
  color: #64748b;
}

html.dark .el-dialog.batch-move-dialog-shell .el-select__caret,
html.dark .batch-move-dialog-shell .el-select__caret {
  color: rgba(148, 163, 184, 0.78);
}

.batch-move-select-popper.el-popper,
.batch-move-select-popper.el-select__popper {
  border: 1px solid #cbd5e1;
  border-radius: 16px;
  background: #ffffff !important;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.14);
}

html.dark .batch-move-select-popper.el-popper,
html.dark .batch-move-select-popper.el-select__popper {
  border: 1px solid rgba(125, 211, 252, 0.14);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.98), rgba(15, 23, 42, 0.98)) !important;
  box-shadow: 0 18px 45px rgba(2, 6, 23, 0.42);
}

.batch-move-select-popper.el-popper .el-popper__arrow::before,
.batch-move-select-popper.el-select__popper .el-popper__arrow::before {
  border: 1px solid #cbd5e1;
  background: #ffffff !important;
}

html.dark .batch-move-select-popper.el-popper .el-popper__arrow::before,
html.dark .batch-move-select-popper.el-select__popper .el-popper__arrow::before {
  border: 1px solid rgba(125, 211, 252, 0.14);
  background: rgba(17, 24, 39, 0.98) !important;
}

.batch-move-select-popper .el-select-dropdown,
.batch-move-select-popper .el-scrollbar,
.batch-move-select-popper .el-scrollbar__view,
.batch-move-select-popper .el-select-dropdown__wrap,
.batch-move-select-popper .el-select-dropdown__list {
  background: transparent !important;
}

.batch-move-select-popper .el-select-dropdown__list {
  padding: 8px;
}

.batch-move-select-popper .el-select-dropdown__item {
  border-radius: 10px;
  color: #1e293b !important;
}

html.dark .batch-move-select-popper .el-select-dropdown__item {
  color: #dbeafe !important;
}

.batch-move-select-popper .el-select-dropdown__item.hover,
.batch-move-select-popper .el-select-dropdown__item:hover,
.batch-move-select-popper .el-select-dropdown__item.is-hovering {
  background: rgba(34, 211, 238, 0.1) !important;
}

html.dark .batch-move-select-popper .el-select-dropdown__item.hover,
html.dark .batch-move-select-popper .el-select-dropdown__item:hover,
html.dark .batch-move-select-popper .el-select-dropdown__item.is-hovering {
  background: rgba(34, 211, 238, 0.12) !important;
}

.batch-move-select-popper .el-select-dropdown__item.selected {
  color: #0891b2 !important;
  font-weight: 600;
}

html.dark .batch-move-select-popper .el-select-dropdown__item.selected {
  color: #a5f3fc !important;
}
</style>
