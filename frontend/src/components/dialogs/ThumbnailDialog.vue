<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from '@/composables/useNotification'
import { Upload, Link } from '@element-plus/icons-vue'
import type { Video } from '@/types/media'
import { getCSRFToken } from '@/composables/GetCSRFToken'
import { BACKEND } from '@/composables/ConfigAPI'

type ThumbTarget = Video

const fileInput = ref<HTMLInputElement | null>(null)

const props = defineProps<{
  modelValue: boolean
  video?: Video | null
  target?: Video | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', visible: boolean): void
  (e: 'target-updated', updated: ThumbTarget): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const thumbnailPreview = ref('')
const thumbnailFile = ref<File | null>(null)
const thumbnailUrlInput = ref('')

function getThumbnailAssetUrl(target?: Video | null) {
  const filename = target?.thumbnail_url || target?.thumbnail || ''
  return filename ? `${BACKEND}/media/thumbnail/${encodeURIComponent(filename)}` : ''
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    thumbnailPreview.value = getThumbnailAssetUrl(props.target)
    thumbnailUrlInput.value = ''
    thumbnailFile.value = null
  },
)

function handlePaste(event: ClipboardEvent) {
  const items = event.clipboardData?.items
  if (!items) return

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind !== 'file' || !item.type.match(/^image\//)) continue

    const file = item.getAsFile()
    if (!file) return
    if (file.size > 5 * 1024 * 1024) {
      ElMessage.error('粘贴的图片不能超过 5MB')
      return
    }

    thumbnailFile.value = file
    thumbnailUrlInput.value = ''

    const reader = new FileReader()
    reader.onload = (e) => {
      thumbnailPreview.value = (e.target?.result as string) || ''
    }
    reader.readAsDataURL(file)
    break
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  if (!file.type.match(/^image\//)) {
    ElMessage.error('请选择有效的图片文件')
    return
  }

  thumbnailFile.value = file
  thumbnailUrlInput.value = ''

  const reader = new FileReader()
  reader.onload = (e) => {
    thumbnailPreview.value = (e.target?.result as string) || ''
  }
  reader.readAsDataURL(file)
}

async function onSubmit() {
  if (!thumbnailPreview.value) {
    ElMessage.error('请选择上传图片或填写图片地址')
    return
  }

  if (!props.target) {
    ElMessage.error('无效的视频对象')
    return
  }

  const formData = new FormData()
  if (thumbnailFile.value) {
    formData.append('thumbnail_file', thumbnailFile.value)
  } else if (thumbnailUrlInput.value) {
    formData.append('thumbnail_url', thumbnailUrlInput.value)
  }

  try {
    const csrfToken = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/${props.target.id}/update_thumbnail`, {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': csrfToken,
      },
      credentials: 'include',
    })

    const data = await response.json()
    if (!data.success) {
      ElMessage.error(data.error || '更新缩略图失败')
      return
    }

    ElMessage.success('缩略图已更新')
    emit('target-updated', {
      ...props.target,
      thumbnail: data.thumbnail_url,
      thumbnail_url: data.thumbnail_url,
    })
    visible.value = false
  } catch (error) {
    console.error(error)
    ElMessage.error('缩略图上传失败')
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="编辑缩略图"
    width="500px"
    class="thumbnail-dialog-shell"
    @close="visible = false"
  >
    <div class="space-y-4 rounded-[20px] bg-[linear-gradient(180deg,rgba(15,23,42,0.84),rgba(17,24,39,0.78))] p-4">
      <div class="grid items-start gap-4 md:grid-cols-[1.1fr_0.9fr]">
        <div class="self-start overflow-hidden rounded-[18px] bg-slate-950/70 shadow-inner">
          <div v-if="thumbnailPreview" class="aspect-video bg-slate-950">
            <img :src="thumbnailPreview" class="h-full w-full object-cover" />
          </div>
          <div
            v-else
            class="flex aspect-video items-center justify-center bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.12),transparent_55%),linear-gradient(180deg,rgba(15,23,42,0.92),rgba(2,6,23,0.96))] text-sm text-slate-400"
          >
            等待新的缩略图
          </div>
        </div>

        <div class="space-y-3">
          <div class="space-y-2">
            <p class="text-sm font-medium text-white">上传图片</p>
            <p class="text-xs leading-5 text-slate-400">
              支持 JPG、PNG 等静态图片，建议 16:9，大小不超过 5MB。
            </p>
            <button
              class="mt-2 inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-cyan-400/22 bg-cyan-500/10 px-4 text-sm font-semibold text-cyan-100 transition hover:border-cyan-300/34 hover:bg-cyan-400/14"
              @click="fileInput?.click()"
            >
              <el-icon><Upload /></el-icon>
              选择图片
            </button>
            <input
              ref="fileInput"
              type="file"
              accept="image/*"
              class="hidden"
              @change="onFileChange"
            />
          </div>
        </div>

        <div class="border-t border-white/8 pt-3 md:col-span-2">
          <label class="mb-2 block text-sm font-medium text-white">图片地址</label>
          <el-input
            v-model="thumbnailUrlInput"
            placeholder="https://example.com/cover.jpg"
            @change="thumbnailPreview = thumbnailUrlInput.trim()"
          >
            <template #prefix>
              <el-icon><Link /></el-icon>
            </template>
          </el-input>
        </div>
      </div>

      <div
        class="rounded-2xl border border-dashed border-white/10 bg-white/[0.025] px-4 py-4 text-center text-sm text-slate-400 transition hover:border-cyan-400/28 hover:bg-cyan-500/[0.04]"
        @paste="handlePaste"
      >
        <p class="font-medium text-slate-200">也可以直接在这里粘贴截图</p>
        <p class="mt-1 text-xs text-slate-500">粘贴后会自动预览，并在提交后替换当前缩略图。</p>
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-3">
        <button
          class="inline-flex h-10 items-center justify-center rounded-xl border border-white/12 bg-white/[0.04] px-4 text-sm font-medium text-slate-200 transition hover:border-white/20 hover:bg-white/[0.08]"
          @click="visible = false"
        >
          取消
        </button>
        <button
          class="inline-flex h-10 items-center justify-center rounded-xl border border-cyan-400/20 bg-[linear-gradient(135deg,rgba(34,211,238,0.24),rgba(59,130,246,0.24))] px-4 text-sm font-semibold text-cyan-50 transition hover:border-cyan-300/35 hover:shadow-[0_12px_28px_rgba(34,211,238,0.16)]"
          @click="onSubmit"
        >
          保存缩略图
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style>
.el-dialog.thumbnail-dialog-shell,
.thumbnail-dialog-shell .el-dialog {
  overflow: hidden;
  border: 1px solid rgba(125, 211, 252, 0.1);
  border-radius: 22px;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.07), transparent 38%),
    linear-gradient(180deg, #111827, #0f172a 52%, #020617);
  box-shadow: 0 24px 56px rgba(2, 6, 23, 0.44);
}

.el-dialog.thumbnail-dialog-shell .el-dialog__header,
.el-dialog.thumbnail-dialog-shell .el-dialog__body,
.el-dialog.thumbnail-dialog-shell .el-dialog__footer,
.thumbnail-dialog-shell .el-dialog__header,
.thumbnail-dialog-shell .el-dialog__body,
.thumbnail-dialog-shell .el-dialog__footer {
  background: transparent;
}

.el-dialog.thumbnail-dialog-shell .el-dialog__header,
.thumbnail-dialog-shell .el-dialog__header {
  margin: 0;
  padding: 18px 18px 6px;
}

.el-dialog.thumbnail-dialog-shell .el-dialog__title,
.thumbnail-dialog-shell .el-dialog__title {
  color: #f8fafc;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.el-dialog.thumbnail-dialog-shell .el-dialog__headerbtn .el-dialog__close,
.thumbnail-dialog-shell .el-dialog__headerbtn .el-dialog__close {
  color: rgba(226, 232, 240, 0.78);
}

.el-dialog.thumbnail-dialog-shell .el-dialog__body,
.thumbnail-dialog-shell .el-dialog__body {
  padding: 10px 18px 14px;
}

.el-dialog.thumbnail-dialog-shell .el-dialog__footer,
.thumbnail-dialog-shell .el-dialog__footer {
  padding: 0 18px 18px;
}

.el-dialog.thumbnail-dialog-shell .el-input__wrapper,
.thumbnail-dialog-shell .el-input__wrapper {
  border: 1px solid rgba(125, 211, 252, 0.12);
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.el-dialog.thumbnail-dialog-shell .el-input__wrapper.is-focus,
.thumbnail-dialog-shell .el-input__wrapper.is-focus {
  box-shadow: 0 0 0 1px rgba(103, 232, 249, 0.28);
  border-color: rgba(103, 232, 249, 0.28);
}

.el-dialog.thumbnail-dialog-shell .el-input__inner,
.thumbnail-dialog-shell .el-input__inner {
  color: #e2e8f0;
}

.el-dialog.thumbnail-dialog-shell .el-input__inner::placeholder,
.thumbnail-dialog-shell .el-input__inner::placeholder {
  color: rgba(148, 163, 184, 0.72);
}

.el-dialog.thumbnail-dialog-shell .el-input__prefix-inner,
.thumbnail-dialog-shell .el-input__prefix-inner {
  color: rgba(125, 211, 252, 0.86);
}
</style>
