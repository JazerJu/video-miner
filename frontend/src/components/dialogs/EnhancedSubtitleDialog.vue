<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from '@/composables/useNotification'
import { getCookie } from '@/composables/GetCSRFToken'

import { BACKEND } from '@/composables/ConfigAPI'

// —— Props ——
const props = defineProps<{
  /** v-model 控制弹窗显隐 */
  modelValue: boolean
  /** 待处理视频 ID 列表  */
  videoIdList: number[]
  /** 与 videoIdList 一一对应的标题，用于后端记录 */
  videoNameList: string[]
  /** 当前视频的原始语言（用于预选择下拉框） */
  currentRawLang?: string
}>()

// —— Emits ——
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  /** 后端提交成功后可通知父组件刷新 */
  (e: 'submitted'): void
}>()

// —— Dialog v-model 代理 ——
const visible = computed<boolean>({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// —— 表单状态 ——
// 优先使用当前视频的rawLang，如果没有则保持之前的选择（默认'zh'）
const srcLang = ref<'zh' | 'en' | 'jp' | 'system_define'>(
  (props.currentRawLang as 'zh' | 'en' | 'jp' | 'system_define') || 'zh',
)
const transLang = ref<'none' | 'zh' | 'en' | 'jp'>('none')
const emphasizeSrc = ref('')
const emphasizeDst = ref('')
const loading = ref(false)

// 新增状态
const actionType = ref<'set_language' | 'generate_bilingual' | 'generate_translation'>(
  'generate_bilingual',
)

// —— API调用函数 ——
async function setVideoLanguage() {
  if (!srcLang.value) {
    ElMessage.warning('请选择视频语言')
    return
  }

  loading.value = true
  const csrfToken = getCookie('csrftoken')

  try {
    // 为每个视频设置语言
    for (const videoId of props.videoIdList) {
      const res = await fetch(`${BACKEND}/api/videos/${videoId}/update_raw_lang`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          raw_lang: srcLang.value,
        }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    }

    ElMessage.success('视频语言设置成功')
    emit('submitted')
    emit('update:modelValue', false)
  } catch (err: any) {
    console.error(err)
    ElMessage.error(`设置失败：${err.message}`)
  } finally {
    loading.value = false
  }
}

async function generateBilingualSubtitles() {
  if (!srcLang.value) {
    ElMessage.warning('请选择原文语言')
    return
  }

  loading.value = true
  const csrfToken = getCookie('csrftoken')

  try {
    const res = await fetch(`${BACKEND}/api/tasks/subtitle_generate/add`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({
        video_id_list: props.videoIdList,
        video_name_list: props.videoNameList,
        src_lang: srcLang.value,
        trans_lang: transLang.value === 'none' ? '' : transLang.value,
        emphasize_src: emphasizeSrc.value,
        emphasize_dst: emphasizeDst.value,
      }),
    })

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    ElMessage.success('已提交双语字幕生成任务')
    emit('submitted')
    emit('update:modelValue', false)
  } catch (err: any) {
    console.error(err)
    ElMessage.error(`提交失败：${err.message}`)
  } finally {
    loading.value = false
  }
}

async function generateTranslationOnly() {
  if (!transLang.value || transLang.value === 'none') {
    ElMessage.warning('请选择翻译语言')
    return
  }

  loading.value = true
  const csrfToken = getCookie('csrftoken')

  try {
    const res = await fetch(`${BACKEND}/api/tasks/subtitle_translation/add`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({
        video_id_list: props.videoIdList,
        video_name_list: props.videoNameList,
        target_lang: transLang.value,
        emphasize_dst: emphasizeDst.value,
      }),
    })

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    ElMessage.success('已提交翻译字幕生成任务')
    emit('submitted')
    emit('update:modelValue', false)
  } catch (err: any) {
    console.error(err)
    ElMessage.error(`提交失败：${err.message}`)
  } finally {
    loading.value = false
  }
}

// —— 主确认函数 ——
async function confirm() {
  switch (actionType.value) {
    case 'set_language':
      await setVideoLanguage()
      break
    case 'generate_bilingual':
      await generateBilingualSubtitles()
      break
    case 'generate_translation':
      await generateTranslationOnly()
      break
  }
}

// 计算标题
const dialogTitle = computed(() => {
  switch (actionType.value) {
    case 'set_language':
      return '设置视频语言'
    case 'generate_bilingual':
      return '生成双语字幕'
    case 'generate_translation':
      return '生成翻译字幕'
    default:
      return '字幕操作'
  }
})

// 计算确认按钮文本
const confirmButtonText = computed(() => {
  switch (actionType.value) {
    case 'set_language':
      return '设置语言'
    case 'generate_bilingual':
      return '生成双语字幕'
    case 'generate_translation':
      return '生成翻译'
    default:
      return '确定'
  }
})
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="430px"
    class="enhanced-subtitle-dialog-shell"
  >
    <div class="space-y-4 rounded-[20px] bg-[linear-gradient(180deg,rgba(15,23,42,0.84),rgba(17,24,39,0.78))] p-4">
      <div class="space-y-3">
        <label class="block text-sm font-medium text-slate-200">操作类型</label>
        <el-radio-group v-model="actionType" class="w-full">
          <div class="space-y-2">
            <el-radio value="set_language" class="w-full !mr-0 rounded-xl border border-white/8 bg-white/[0.025] px-3 py-2.5">
              <span class="text-slate-200">设置视频语言（用于正确展示字幕）</span>
            </el-radio>
            <el-radio value="generate_bilingual" class="w-full !mr-0 rounded-xl border border-white/8 bg-white/[0.025] px-3 py-2.5">
              <span class="text-slate-200">生成双语字幕（原文+翻译）</span>
            </el-radio>
            <el-radio value="generate_translation" class="w-full !mr-0 rounded-xl border border-white/8 bg-white/[0.025] px-3 py-2.5">
              <span class="text-slate-200">仅生成翻译字幕（基于已有原文）</span>
            </el-radio>
          </div>
        </el-radio-group>
      </div>

      <div class="space-y-4 border-t border-white/8 pt-4">
        <div v-if="actionType === 'set_language' || actionType === 'generate_bilingual'">
          <label class="mb-2 block text-sm font-medium text-slate-300">
            {{ actionType === 'set_language' ? '视频语言' : '原文语言' }}
          </label>
          <el-select
            v-model="srcLang"
            placeholder="选择语言"
            class="w-full"
            popper-class="enhanced-subtitle-select-popper"
            :teleported="false"
          >
            <el-option label="中文 (zh)" value="zh" />
            <el-option label="English (en)" value="en" />
            <el-option label="日本語 (jp)" value="jp" />
            <el-option
              v-if="actionType === 'generate_bilingual'"
              label="System Define"
              value="system_define"
            />
          </el-select>
        </div>

        <div v-if="actionType === 'generate_bilingual' || actionType === 'generate_translation'">
          <label class="mb-2 block text-sm font-medium text-slate-300">
            {{ actionType === 'generate_bilingual' ? '译文语言' : '翻译目标语言' }}
          </label>
          <el-select
            v-model="transLang"
            placeholder="选择译文语言"
            class="w-full"
            popper-class="enhanced-subtitle-select-popper"
            :teleported="false"
          >
            <el-option v-if="actionType === 'generate_bilingual'" label="无 (None)" value="none" />
            <el-option label="中文 (zh)" value="zh" />
            <el-option label="English (en)" value="en" />
            <el-option label="日本語 (jp)" value="jp" />
          </el-select>
        </div>

        <div v-if="actionType === 'generate_bilingual' || actionType === 'generate_translation'">
          <label class="mb-2 block text-sm font-medium text-slate-300">译文强调名词</label>
          <el-input
            v-model="emphasizeDst"
            type="textarea"
            :rows="2"
            placeholder="译文中需强调的名词（仅本地记录，可留空）"
          />
        </div>
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-3">
        <button
          class="inline-flex h-10 items-center justify-center rounded-xl border border-white/12 bg-white/[0.04] px-4 text-sm font-medium text-slate-200 transition hover:border-white/20 hover:bg-white/[0.08]"
          @click="emit('update:modelValue', false)"
        >
          取消
        </button>
        <button
          class="inline-flex h-10 items-center justify-center rounded-xl border border-cyan-400/20 bg-[linear-gradient(135deg,rgba(34,211,238,0.24),rgba(59,130,246,0.24))] px-4 text-sm font-semibold text-cyan-50 transition hover:border-cyan-300/35 hover:shadow-[0_12px_28px_rgba(34,211,238,0.16)] disabled:cursor-not-allowed disabled:opacity-65"
          :disabled="loading"
          @click="confirm"
        >
          {{ loading ? '提交中...' : confirmButtonText }}
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
:deep(.el-radio) {
  height: auto;
  align-items: flex-start;
}

:deep(.el-radio__input) {
  margin-top: 2px;
}

:deep(.el-radio__label) {
  white-space: normal;
  line-height: 1.5;
}
</style>

<style>
.el-dialog.enhanced-subtitle-dialog-shell,
.enhanced-subtitle-dialog-shell .el-dialog {
  overflow: hidden;
  border: 1px solid rgba(125, 211, 252, 0.1);
  border-radius: 22px;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.07), transparent 38%),
    linear-gradient(180deg, #111827, #0f172a 52%, #020617);
  box-shadow: 0 24px 56px rgba(2, 6, 23, 0.44);
}

.el-dialog.enhanced-subtitle-dialog-shell .el-dialog__header,
.el-dialog.enhanced-subtitle-dialog-shell .el-dialog__body,
.el-dialog.enhanced-subtitle-dialog-shell .el-dialog__footer,
.enhanced-subtitle-dialog-shell .el-dialog__header,
.enhanced-subtitle-dialog-shell .el-dialog__body,
.enhanced-subtitle-dialog-shell .el-dialog__footer {
  background: transparent;
}

.el-dialog.enhanced-subtitle-dialog-shell .el-dialog__header,
.enhanced-subtitle-dialog-shell .el-dialog__header {
  margin: 0;
  padding: 18px 18px 6px;
}

.el-dialog.enhanced-subtitle-dialog-shell .el-dialog__title,
.enhanced-subtitle-dialog-shell .el-dialog__title {
  color: #f8fafc;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.el-dialog.enhanced-subtitle-dialog-shell .el-dialog__headerbtn .el-dialog__close,
.enhanced-subtitle-dialog-shell .el-dialog__headerbtn .el-dialog__close {
  color: rgba(226, 232, 240, 0.78);
}

.el-dialog.enhanced-subtitle-dialog-shell .el-dialog__body,
.enhanced-subtitle-dialog-shell .el-dialog__body {
  padding: 10px 18px 14px;
}

.el-dialog.enhanced-subtitle-dialog-shell .el-dialog__footer,
.enhanced-subtitle-dialog-shell .el-dialog__footer {
  padding: 0 18px 18px;
}

.el-dialog.enhanced-subtitle-dialog-shell .el-input__wrapper,
.el-dialog.enhanced-subtitle-dialog-shell .el-select__wrapper,
.enhanced-subtitle-dialog-shell .el-input__wrapper,
.enhanced-subtitle-dialog-shell .el-select__wrapper {
  border: 1px solid rgba(125, 211, 252, 0.12);
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.el-dialog.enhanced-subtitle-dialog-shell .el-input__wrapper.is-focus,
.el-dialog.enhanced-subtitle-dialog-shell .el-select__wrapper.is-focused,
.enhanced-subtitle-dialog-shell .el-input__wrapper.is-focus,
.enhanced-subtitle-dialog-shell .el-select__wrapper.is-focused {
  box-shadow: 0 0 0 1px rgba(103, 232, 249, 0.28);
  border-color: rgba(103, 232, 249, 0.28);
}

.el-dialog.enhanced-subtitle-dialog-shell .el-input__inner,
.el-dialog.enhanced-subtitle-dialog-shell .el-textarea__inner,
.el-dialog.enhanced-subtitle-dialog-shell .el-select__placeholder,
.el-dialog.enhanced-subtitle-dialog-shell .el-select__selected-item,
.enhanced-subtitle-dialog-shell .el-input__inner,
.enhanced-subtitle-dialog-shell .el-textarea__inner,
.enhanced-subtitle-dialog-shell .el-select__placeholder,
.enhanced-subtitle-dialog-shell .el-select__selected-item {
  color: #e2e8f0;
}

.el-dialog.enhanced-subtitle-dialog-shell .el-input__inner::placeholder,
.el-dialog.enhanced-subtitle-dialog-shell .el-textarea__inner::placeholder,
.enhanced-subtitle-dialog-shell .el-input__inner::placeholder,
.enhanced-subtitle-dialog-shell .el-textarea__inner::placeholder {
  color: rgba(148, 163, 184, 0.72);
}

.el-dialog.enhanced-subtitle-dialog-shell .el-textarea__inner,
.enhanced-subtitle-dialog-shell .el-textarea__inner {
  border: 1px solid rgba(125, 211, 252, 0.12);
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.el-dialog.enhanced-subtitle-dialog-shell .el-radio,
.enhanced-subtitle-dialog-shell .el-radio {
  margin-right: 0;
}

.el-dialog.enhanced-subtitle-dialog-shell .el-radio__inner,
.enhanced-subtitle-dialog-shell .el-radio__inner {
  border-color: rgba(148, 163, 184, 0.55);
  background: rgba(15, 23, 42, 0.86);
}

.el-dialog.enhanced-subtitle-dialog-shell .el-radio__input.is-checked .el-radio__inner,
.enhanced-subtitle-dialog-shell .el-radio__input.is-checked .el-radio__inner {
  border-color: rgba(56, 189, 248, 0.88);
  background: rgba(56, 189, 248, 0.88);
}

.el-dialog.enhanced-subtitle-dialog-shell .el-radio__input.is-checked + .el-radio__label,
.enhanced-subtitle-dialog-shell .el-radio__input.is-checked + .el-radio__label {
  color: #f8fafc;
}

.enhanced-subtitle-select-popper.el-popper,
.enhanced-subtitle-select-popper.el-select__popper {
  border: 1px solid rgba(125, 211, 252, 0.14);
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.98), rgba(15, 23, 42, 0.98)) !important;
  box-shadow: 0 18px 45px rgba(2, 6, 23, 0.42);
}

.enhanced-subtitle-select-popper.el-popper .el-popper__arrow::before,
.enhanced-subtitle-select-popper.el-select__popper .el-popper__arrow::before {
  border: 1px solid rgba(125, 211, 252, 0.14);
  background: rgba(17, 24, 39, 0.98) !important;
}

.enhanced-subtitle-select-popper .el-select-dropdown,
.enhanced-subtitle-select-popper .el-scrollbar,
.enhanced-subtitle-select-popper .el-scrollbar__view,
.enhanced-subtitle-select-popper .el-select-dropdown__wrap,
.enhanced-subtitle-select-popper .el-select-dropdown__list {
  background: transparent !important;
}

.enhanced-subtitle-select-popper .el-select-dropdown__list {
  padding: 8px;
}

.enhanced-subtitle-select-popper .el-select-dropdown__item {
  border-radius: 10px;
  color: #dbeafe !important;
}

.enhanced-subtitle-select-popper .el-select-dropdown__item.hover,
.enhanced-subtitle-select-popper .el-select-dropdown__item:hover,
.enhanced-subtitle-select-popper .el-select-dropdown__item.is-hovering {
  background: rgba(34, 211, 238, 0.12) !important;
}

.enhanced-subtitle-select-popper .el-select-dropdown__item.selected {
  color: #a5f3fc !important;
  font-weight: 600;
}
</style>
