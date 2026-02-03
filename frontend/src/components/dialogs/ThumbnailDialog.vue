<!-- src/components/ThumbnailDialog.vue -->
<script setup lang="ts">
import { defineProps, defineEmits, ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Link } from '@element-plus/icons-vue'
import type { Video } from '@/types/media'
import { getCSRFToken } from '@/composables/GetCSRFToken'

const fileInput = ref<HTMLInputElement | null>(null)
import { BACKEND } from '@/composables/ConfigAPI'

const props = defineProps<{
  modelValue: boolean
  video?: Video | null
  target?: Video | null
}>()

const emit = defineEmits<{
  /** update the v-model */
  (e: 'update:modelValue', visible: boolean): void
  /** notify parent that thumbnail was updated */
  (e: 'target-updated', updated: ThumbTarget): void
}>()

const visible = computed<boolean>({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

type ThumbTarget = Video

const thumbnailPreview = ref<string>('')
const thumbnailFile = ref<File | null>(null)
const thumbnailUrlInput = ref<string>('')

function isVideo(t: Video): t is Video {
  return true
}

watch(
  () => props.modelValue,
  (open) => {
    if (open && props.target) {
      const filename = props.target?.thumbnail || 'default'
      const thumbnailUrl = `${BACKEND}/media/${encodeURIComponent(filename)}`
      thumbnailPreview.value = thumbnailUrl || ''
      thumbnailUrlInput.value = thumbnailUrl || ''
      thumbnailFile.value = null
    }
  },
)

function handlePaste(event: ClipboardEvent) {
  const items = event.clipboardData?.items
  if (!items) return

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind === 'file' && item.type.match(/^image\//)) {
      const file = item.getAsFile()
      if (!file) return

      if (file.size > 5 * 1024 * 1024) {
        ElMessage.error('粘贴的图片不能超过5M')
        return
      }

      thumbnailFile.value = file
      thumbnailUrlInput.value = ''
      const reader = new FileReader()
      reader.onload = (e) => {
        thumbnailPreview.value = e.target?.result as string
      }
      reader.readAsDataURL(file)
      break
    }
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
    thumbnailPreview.value = e.target?.result as string
  }
  reader.readAsDataURL(file)
}

async function onSubmit() {
  if (!thumbnailPreview.value) {
    ElMessage.error('请选择或粘贴图片')
    return
  }
  if (!props.target) {
    ElMessage.error('无效的操作：缺少 video')
    return
  }

  const formData = new FormData()
  if (thumbnailFile.value) {
    formData.append('thumbnail_file', thumbnailFile.value)
  } else if (thumbnailUrlInput.value) {
    formData.append('thumbnail_url', thumbnailUrlInput.value)
  }
  let url = ''
  if (isVideo(props.target)) {
    url = `${BACKEND}/api/videos/${props.target.id}/update_thumbnail`
  }
  try {
    const csrfToken = await getCSRFToken()
    const resp = await fetch(url, {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': csrfToken,
      },
      credentials: 'include', // 确保 fetch 请求会携带 cookie
    })
    const data = await resp.json()
    if (data.success) {
      ElMessage.success('缩略图已更新')
      const updated: ThumbTarget = {
        ...props.target,
        thumbnail: data.thumbnail_url,
      }
      // 传target，让上一级判断是修改Collection还是Video.
      emit('target-updated', updated)
    } else {
      ElMessage.error(data.error || '更新缩略图失败')
    }
  } catch (err) {
    console.error(err)
    ElMessage.error('缩略图上传失败')
  } finally {
    visible.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="编辑缩略图" width="500px">
    <div class="grid grid-cols-2 gap-4">
      <!-- file picker -->
      <div>
        <el-button type="primary" @click="fileInput?.click()">
          <el-icon><Upload /></el-icon> 选择图片
        </el-button>
        <input type="file" ref="fileInput" accept="image/*" class="hidden" @change="onFileChange" />
      </div>
      <!-- URL input -->
      <div>
        <el-input
          v-model="thumbnailUrlInput"
          placeholder="输入图片 URL"
          @change="thumbnailPreview = thumbnailUrlInput"
        >
          <template #prefix>
            <el-icon><Link /></el-icon>
          </template>
        </el-input>
      </div>
    </div>

    <!-- preview -->
    <div v-if="thumbnailPreview" class="mt-4 text-center">
      <img :src="thumbnailPreview" class="max-h-64 mx-auto rounded border" />
    </div>

    <!-- paste zone -->
    <div
      class="mt-4 p-4 border-2 border-dashed rounded-lg text-center cursor-pointer hover:bg-gray-50"
      @paste="handlePaste"
    >
      <p class="text-gray-500">或直接在此区域粘贴图片</p>
      <p class="text-xs text-gray-400">支持JPG/PNG等静态图片格式，大小不超过5M</p>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onSubmit">提交</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* optional extra styling */
</style>
