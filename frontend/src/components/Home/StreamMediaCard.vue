<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { defineExpose, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Link, Document, Microphone, Finished, ArrowDown } from '@element-plus/icons-vue'
import { getCSRFToken, getCookie } from '@/composables/GetCSRFToken'
import type { RequestVideo } from '@/types/media'
import { useI18n } from 'vue-i18n'

// 定义事件发射
const emit = defineEmits<{
  (e: 'upload-complete'): void
}>()

// i18n functionality
const { t } = useI18n()

// 首页函数
// 获取视频预览信息
const proxyThumbnailUrl = computed(() => {
  return `${BACKEND}/media/thumbnail/?url=${encodeURIComponent(requestVideo.value.thumbnail)}`
})
const inputUrl = ref('')
async function submitUrl() {
  if (!inputUrl.value) return alert(t('pleaseEnterUrl'))
  const csrfToken = await getCSRFToken()
  try {
    const res = await fetch(`${BACKEND}/api/stream_media/query`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({ url: inputUrl.value }),
    })

    const data = await res.json()
    console.log(data)
    // 将 data 映射到 requestVideo 上
    requestVideo.value = {
      url: inputUrl.value,
      bvid: data.bvid,
      title: data.title, // 标题
      thumbnail: data.thumbnail, // 缩略图 URL
      collectionCount: data.collectionCount, // 同合集视频数量
      duration: data.length || data.duration, // 时长，取后端字段名
      owner: data.owner || '', // 作者或其他字段
      video_data: data.video_data ?? [], // 👈  新增
    }
  } catch (e) {
    console.error('请求失败：', e)
  }
}

// 输入链接预览视频
const requestVideo = ref<RequestVideo>({
  url: '',
  bvid: '',
  title: '默认视频',
  thumbnail: '',
  collectionCount: 0,
  duration: 0,
  owner: 'jjz',
  video_data: [],
})

// 选择视频
let lastIndex: number | null = null
const selectedParts = ref<Array<number>>([])
// 单独写个函数；这里是“脚本”作用域，selectedParts 仍是 Ref
function updateSelected(val: number[]) {
  selectedParts.value = val
}

const allCids = computed<number[]>(() =>
  requestVideo.value ? requestVideo.value.video_data.map((v) => v.cid) : [],
)

function toggleRange(idx: number, checked: boolean) {
  if (lastIndex === null) {
    lastIndex = idx
    return
  }
  // 计算两个索引间的区间
  const [start, end] = idx > lastIndex ? [lastIndex, idx] : [idx, lastIndex]
  const range = Array.from({ length: end - start + 1 }, (_, i) => start + i)

  if (checked) {
    // 勾选：并集
    selectedParts.value = Array.from(new Set([...selectedParts.value, ...range]))
  } else {
    // 取消：差集
    selectedParts.value = selectedParts.value.filter((i) => !range.includes(i))
  }
}

// function onCheckChange(idx: number, checked: boolean) {
//   if (isShiftDown.value) {
//     toggleRange(idx, checked)
//   } else {
//     lastIndex = idx
//     // 单体勾选/反勾
//     if (checked) {
//       selectedParts.value.push(idx)
//     } else {
//       selectedParts.value = selectedParts.value.filter((i) => i !== idx)
//     }
//   }
// }

function onCheckChange(idx: number, checked: boolean) {
  if (isShiftDown.value) {
    toggleRange(idx, checked)
  } else {
    lastIndex = idx // 让 CheckboxGroup 自己更新
  }
}

/* 点击“开始下载” */
async function confirmDownload() {
  if (!requestVideo.value) return
  console.log(requestVideo.value)
  console.log(selectedParts.value)
  /* 若没选，默认全选 */
  const cids =
    selectedParts.value.length === 0
      ? allCids.value
      : selectedParts.value.map((idx) => requestVideo.value!.video_data[idx].cid)
  const parts =
    selectedParts.value.length === 0
      ? allCids.value
      : selectedParts.value.map((idx) => requestVideo.value!.video_data[idx].part)
  const durations =
    selectedParts.value.length === 0
      ? requestVideo.value!.video_data.map((item) => item.duration)
      : selectedParts.value.map((idx) => requestVideo.value!.video_data[idx].duration)
  const filename = requestVideo.value.title
  // 调用后端 ↓↓↓
  try {
    const csrfToken = getCookie('csrftoken')
    const res = await fetch(`${BACKEND}/api/stream_media/download/add`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({
        url: requestVideo.value.url,
        bvid: requestVideo.value.bvid,
        cids: cids,
        parts: parts,
        durations: durations,
        filename: filename,
      }),
    })
    const { task_id } = await res.json()
    ElMessage.success(t('downloadTaskSubmitted', { taskId: task_id }))
    selectedParts.value = [] // 清空勾选
  } catch (e) {
    ElMessage.error(t('downloadTaskFailed'))
  }
}

import { BACKEND } from '@/composables/ConfigAPI'

// Tracks multi-file upload progress
interface UploadTask {
  id: number
  name: string
  progress: number
  status: 'uploading' | 'success' | 'error'
}
const uploadTasks = ref<UploadTask[]>([])

// Hidden file input ref for uploads
const fileInput = ref<HTMLInputElement | null>(null)

// Multi-file upload handler with progress
async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files || !files.length) return

  uploadTasks.value = []
  Array.from(files).forEach((file, idx) => {
    uploadTasks.value.push({ id: idx, name: file.name, progress: 0, status: 'uploading' })
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append('video_file', file)
    xhr.open('POST', `${BACKEND}/api/videos/0/upload`, true)
    xhr.withCredentials = true
    xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'))
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        uploadTasks.value[idx].progress = Math.round((e.loaded / e.total) * 100)
      }
    }
    xhr.onload = () => {
      const task = uploadTasks.value[idx]
      if (xhr.status === 200 || xhr.status === 201) {
        task.status = 'success'
        ElMessage.success(`「${file.name}」${t('uploadSuccess')}`)
      } else {
        task.status = 'error'
        ElMessage.error(`「${file.name}」${t('uploadFailed')}：${xhr.statusText}`)
      }
      if (uploadTasks.value.every((t) => t.status !== 'uploading')) {
        emit('upload-complete')
      }
    }
    xhr.onerror = () => {
      uploadTasks.value[idx].status = 'error'
      ElMessage.error(`「${file.name}」${t('uploadError')}`)
      if (uploadTasks.value.every((t) => t.status !== 'uploading')) {
        emit('upload-complete')
      }
    }
    xhr.send(formData)
  })
  input.value = ''
}

// 触发文件选择
function triggerFileUpload() {
  fileInput.value?.click()
}

// Handle files dropped into upload area
function handleDrop(event: DragEvent) {
  event.preventDefault()
  const files = event.dataTransfer?.files
  if (!files || !files.length) return
  handleFileChange({ target: { files } } as unknown as Event)
}

// 保存 shift 键当前状态
const isShiftDown = ref(false)
onMounted(() => {
  const down = (e: KeyboardEvent) => {
    if (e.key === 'Shift') isShiftDown.value = true
  }
  const up = (e: KeyboardEvent) => {
    if (e.key === 'Shift') isShiftDown.value = false
  }
  window.addEventListener('keydown', down)
  window.addEventListener('keyup', up)
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', down)
    window.removeEventListener('keyup', up)
  })
})
</script>
<template>
  <!-- 视频链接输入区域 -->
  <div class="mb-8">
    <div
      class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-600/50 shadow-2xl"
    >
      <h2 class="text-xl font-bold text-white mb-6 text-center">{{ t('videoLink') }}</h2>

      <!-- URL输入框区域 -->
      <div class="flex items-stretch mb-4">
        <input
          v-model="inputUrl"
          :placeholder="t('linkPlaceholder')"
          class="flex-1 px-4 py-3 bg-slate-700/70 text-white border border-slate-600/50 border-r-0 rounded-l-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 placeholder-slate-400 transition-all"
        />
        <button
          @click="submitUrl"
          class="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-r-xl border border-blue-600 transition-colors flex items-center justify-center font-medium"
        >
          {{ t('parseBtn') }}
        </button>
      </div>

      <div class="text-center text-slate-400 text-sm">{{ t('orText') }}</div>

      <!-- 本地文件上传区域 -->
      <div class="mt-4">
        <div
          class="block border-2 border-dashed border-slate-600/50 rounded-xl p-8 text-center hover:border-slate-500/70 transition-colors cursor-pointer bg-slate-800/30"
          @click="triggerFileUpload"
          @dragover.prevent
          @drop.prevent="handleDrop"
        >
          <div class="flex flex-col items-center">
            <div
              class="w-12 h-12 rounded-full bg-slate-600/50 flex items-center justify-center mb-4"
            >
              <svg
                class="w-6 h-6 text-slate-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
            </div>
            <h3 class="text-lg font-semibold text-white mb-2">{{ t('clickUploadMedia') }}</h3>
            <p class="text-slate-400 text-sm">{{ t('supportedFormats') }}</p>
          </div>
        </div>

        <!-- 隐藏的文件输入框 -->
        <input
          ref="fileInput"
          type="file"
          accept="video/*,audio/*"
          multiple
          class="hidden"
          @change="handleFileChange"
        />
      </div>
    </div>
  </div>
  <!-- 已解析视频卡片 -->
  <div v-if="requestVideo" class="mb-8">
    <div
      class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-600/50 shadow-2xl"
    >
      <h2 class="text-xl font-bold text-white mb-6 text-center">{{ t('parsedVideo') }}</h2>

      <div
        class="flex items-center gap-6 p-4 bg-slate-700/50 rounded-xl border border-slate-600/30"
      >
        <!-- 左侧缩略图 -->
        <div class="flex-shrink-0">
          <img
            :src="proxyThumbnailUrl"
            :alt="t('videoThumbnail')"
            class="w-20 h-16 object-cover rounded-lg border border-slate-600/50"
          />
        </div>

        <!-- 中间视频信息 -->
        <div class="flex-1 min-w-0">
          <h3 class="text-white font-medium truncate mb-1">{{ requestVideo.title }}</h3>
          <div class="flex items-center gap-4 text-sm text-slate-400">
            <span>{{ t('duration') }}: {{ requestVideo.duration }}</span>
            <span v-if="requestVideo.collectionCount > 1">{{ t('parsed') }}</span>
          </div>
        </div>

        <!-- 右侧下载按钮 -->
        <div class="flex-shrink-0">
          <el-dropdown trigger="click" placement="bottom-end">
            <el-button type="primary" class="bg-blue-600 hover:bg-blue-700 border-blue-600">
              {{ t('downloadVideo') }}
              <el-icon class="ml-1"><ArrowDown /></el-icon>
            </el-button>

            <!-- 下拉框内容 -->
            <template #dropdown>
              <div
                class="bg-slate-800 border border-slate-600 rounded-lg shadow-xl p-4 min-w-[300px]"
              >
                <!-- 复选框组 -->
                <el-checkbox-group
                  v-model="selectedParts"
                  class="space-y-2 max-h-60 overflow-y-auto"
                >
                  <el-checkbox
                    v-for="(item, idx) in requestVideo.video_data"
                    :key="item.cid"
                    :label="idx"
                    @change="(checked: boolean) => onCheckChange(idx, checked)"
                    class="block p-2 hover:bg-slate-700/50 rounded text-white"
                  >
                    <span class="text-blue-400 font-medium">P{{ idx + 1 }}</span>
                    <span class="ml-2 text-slate-200">{{ item.part }}</span>
                  </el-checkbox>
                </el-checkbox-group>

                <!-- 操作按钮 -->
                <div class="mt-4 pt-3 border-t border-slate-600">
                  <el-button
                    type="primary"
                    size="default"
                    class="w-full bg-green-600 hover:bg-green-700 border-green-600"
                    @click.stop="confirmDownload"
                  >
                    {{ t('startDownload') }}
                  </el-button>
                </div>
              </div>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>
  </div>

  <!-- Upload progress floating panel -->
  <div v-if="uploadTasks.length" class="fixed bottom-4 right-4 w-80 space-y-2 z-50">
    <div
      v-for="task in uploadTasks"
      :key="task.id"
      class="bg-slate-800 bg-opacity-90 p-2 rounded-lg shadow-md"
    >
      <div class="text-xs text-white mb-1 truncate">{{ task.name }}</div>
      <el-progress
        :percentage="task.progress"
        :status="
          task.status === 'error' ? 'exception' : task.status === 'success' ? 'success' : undefined
        "
        :stroke-width="6"
        text-inside
        show-text
      />
    </div>
  </div>
</template>
