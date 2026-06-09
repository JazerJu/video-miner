<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { ElMessage } from '@/composables/useNotification'
import { Refresh, More } from '@element-plus/icons-vue'
import { getCookie } from '@/composables/GetCSRFToken'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'

interface TaskRow {
  id: number
  fileName: string
  transcribe: TaskStageStatus
  optimize: TaskStageStatus
  translate: TaskStageStatus
  totalProgress: number  // 🆕 总进度百分比
}

type TaskStageStatus = 'Queued' | 'Running' | 'Completed' | 'Failed'

interface SubtitleTaskInfo {
  video_id: number
  filename: string
  src_lang: 'zh' | 'en' | 'jp' | 'system_define'
  trans_lang: 'None' | 'zh' | 'en' | 'jp'
  stages: {
    transcribe: TaskStageStatus
    optimize: TaskStageStatus
    translate: TaskStageStatus
  }
  total_progress: number  // 🆕 总进度
}

interface DownloadTaskRow {
  id: string
  bvid: string
  fileName: string
  video: string
  audio: string
  merge: string
  totalProgress: number  // 🆕 总进度百分比
}

interface DownloadTaskInfo {
  bvid: string
  title: string
  stages: {
    video: string
    audio: string
    merge: string
  }
  total_progress: number // 🆕 总进度
}

interface SummaryTaskRow {
  id: string
  videoName: string
  build: string
  extract: string
  summarize: string
  totalProgress: number
  resultPath: string
  errorMessage: string
}

interface SummaryTaskInfo {
  video_id: number
  video_name: string
  stages: {
    build: string
    extract: string
    summarize: string
  }
  stage_progress: {
    build: number
    extract: number
    summarize: number
  }
  total_progress: number
  status: string
  result_path: string
  error_message: string
}

import { BACKEND } from '@/composables/ConfigAPI'
import { useUploadTasks } from '@/composables/useUploadTasks'

const { uploadTasks, clearFinished } = useUploadTasks()

const TASKS_URL = '/api/tasks/subtitle_generate/status'
const DOWNLOAD_STATUS_URL = '/api/stream_media/download_status'
const SUMMARY_STATUS_URL = '/api/summary/status'
const POLL_INTERVAL = 3_000

// i18n functionality
const { t } = useI18n()
const { theme } = useTheme()

const isDark = computed(() => theme.value === 'dark')

const headerCellStyle = computed(() =>
  isDark.value
    ? { background: '#1e293b', color: '#e2e8f0', borderColor: '#475569' }
    : { background: '#f8fafc', color: '#1e293b', borderColor: '#e2e8f0' },
)

const cellStyle = computed(() =>
  isDark.value
    ? { background: '#334155', color: '#e2e8f0', borderColor: '#475569' }
    : { background: '#ffffff', color: '#1e293b', borderColor: '#e2e8f0' },
)

const rowStyle = computed(() =>
  isDark.value ? { background: '#334155' } : { background: '#ffffff' },
)

const tableStyle = computed(() =>
  isDark.value ? 'width: 100%; background: #334155' : 'width: 100%; background: #ffffff',
)

const subtitleTasks = ref<TaskRow[]>([])
const downloadTasks = ref<DownloadTaskRow[]>([])
const summaryTasks = ref<SummaryTaskRow[]>([])
let timer_download: number | undefined
let timer_subtitle: number | undefined
let timer_summary: number | undefined

async function fetchSubtitleTasks() {
  try {
    const res = await fetch(`${BACKEND}${TASKS_URL}`, { credentials: 'include' })
    if (!res.ok) throw new Error(await res.text())

    const raw = (await res.json()) as Record<string, SubtitleTaskInfo>

    subtitleTasks.value = Object.entries(raw).map(([id, info]) => ({
      id: +id,
      fileName: info.filename,
      transcribe: info.stages.transcribe,
      optimize: info.stages.optimize,
      translate: info.stages.translate,
      totalProgress: info.total_progress || 0,  // 🆕 总进度
    }))
  } catch (err) {
    ElMessage.error(`${t('taskListFailed')}：${err}`)
  }
}
async function fetchDownloadTasks() {
  try {
    const res = await fetch(`${BACKEND}${DOWNLOAD_STATUS_URL}`, { credentials: 'include' })
    if (!res.ok) throw new Error(await res.text())

    const raw = (await res.json()) as Record<string, DownloadTaskInfo>

    downloadTasks.value = Object.entries(raw).map(([id, info]) => ({
      id: id,
      bvid: info.bvid,
      fileName: info.title,
      video: info.stages.video,
      audio: info.stages.audio,
      merge: info.stages.merge,
      totalProgress: info.total_progress || 0,  // 🆕 总进度
    }))
  } catch (err) {
    ElMessage.error(`${t('taskListFailed')}：${err}`)
  }
}

async function fetchSummaryTasks() {
  try {
    const res = await fetch(`${BACKEND}${SUMMARY_STATUS_URL}`, { credentials: 'include' })
    if (!res.ok) throw new Error(await res.text())

    const raw = (await res.json()) as Record<string, SummaryTaskInfo>

    summaryTasks.value = Object.entries(raw).map(([id, info]) => ({
      id: id,
      videoName: info.video_name,
      build: info.stages.build,
      extract: info.stages.extract,
      summarize: info.stages.summarize,
      totalProgress: info.total_progress || 0,
      resultPath: info.result_path,
      errorMessage: info.error_message,
    }))
  } catch (err) {
    // silent - summary may not be configured
  }
}

type Command = 'retry' | 'delete'
const csrfToken = getCookie('csrftoken')

async function retrySubtitle(id: number) {
  try {
    const res = await fetch(`${BACKEND}/api/tasks/subtitle_generate/${id}/retry`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
    })
    if (!res.ok) throw new Error(await res.text())
    ElMessage.success(t('subtitleTaskRescheduled'))
    await fetchSubtitleTasks()
  } catch (err: any) {
    ElMessage.error(`${t('retryFailed')}：${err.message}`)
  }
}

async function deleteSubtitle(id: number) {
  try {
    const res = await fetch(`${BACKEND}/api/tasks/subtitle_generate/${id}/delete`, {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
    })
    if (!res.ok) throw new Error(await res.text())
    ElMessage.success(t('subtitleTaskDeleted'))
    await fetchSubtitleTasks()
  } catch (err: any) {
    ElMessage.error(`${t('deleteFailed')}：${err.message}`)
  }
}

// 下载任务重试／删除各自的 async 函数
async function retryDownload(id: string) {
  try {
    const res = await fetch(`${BACKEND}/api/stream_media/download/${id}/retry`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
    })
    if (!res.ok) throw new Error(await res.text())
    ElMessage.success(t('downloadTaskRescheduled'))
    await fetchDownloadTasks()
  } catch (err: any) {
    ElMessage.error(`${t('retryFailed')}：${err.message}`)
  }
}

async function deleteDownload(id: string) {
  try {
    const res = await fetch(`${BACKEND}/api/stream_media/download/${id}/delete`, {
      method: 'DELETE',
      credentials: 'include',
    })
    if (!res.ok) throw new Error(await res.text())
    ElMessage.success(t('downloadTaskDeleted'))
    await fetchDownloadTasks()
  } catch (err: any) {
    ElMessage.error(`${t('deleteFailed')}：${err.message}`)
  }
}

async function retrySummary(id: string) {
  try {
    const res = await fetch(`${BACKEND}/api/summary/${id}/retry`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    })
    if (!res.ok) throw new Error(await res.text())
    ElMessage.success('摘要任务已重新排队')
    await fetchSummaryTasks()
  } catch (err: any) {
    ElMessage.error(`${t('retryFailed')}：${err.message}`)
  }
}

async function deleteSummary(id: string) {
  try {
    const res = await fetch(`${BACKEND}/api/summary/${id}/delete`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    })
    if (!res.ok) throw new Error(await res.text())
    ElMessage.success('摘要任务已删除')
    await fetchSummaryTasks()
  } catch (err: any) {
    ElMessage.error(`${t('deleteFailed')}：${err.message}`)
  }
}

function handleCommand(row: TaskRow | DownloadTaskRow | SummaryTaskRow, command: Command): void {
  console.log('handleCommand → row:', row, 'command:', command)
  if (command === 'retry') {
    if ('build' in row) {
      retrySummary(row.id)
    } else if ('bvid' in row) {
      retryDownload(row.id)
    } else {
      retrySubtitle(row.id)
    }
  } else {
    if ('build' in row) {
      deleteSummary(row.id)
    } else if ('bvid' in row) {
      deleteDownload(row.id)
    } else {
      deleteSubtitle(row.id)
    }
  }
}

onMounted(() => {
  fetchDownloadTasks()
  fetchSubtitleTasks()
  fetchSummaryTasks()
  timer_download = window.setInterval(fetchDownloadTasks, POLL_INTERVAL)
  timer_subtitle = window.setInterval(fetchSubtitleTasks, POLL_INTERVAL)
  timer_summary = window.setInterval(fetchSummaryTasks, POLL_INTERVAL)
})

onBeforeUnmount(() => {
  clearInterval(timer_download)
  clearInterval(timer_subtitle)
  clearInterval(timer_summary)
})
</script>

<template>
  <!-- 文件上传任务 -->
  <div v-if="uploadTasks.length" class="mb-8">
    <div
      class="bg-gradient-to-r from-white to-slate-50 dark:from-slate-800/90 dark:to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-200 dark:border-slate-600/50 shadow-2xl"
    >
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-bold text-slate-900 dark:text-white">文件上传</h2>
        <el-button
          type="primary"
          size="small"
          class="bg-blue-600 hover:bg-blue-700 border-blue-600"
          @click="clearFinished"
        >
          清除已完成
        </el-button>
      </div>

      <el-table
        :data="uploadTasks"
        class="dark-table"
        :header-cell-style="headerCellStyle"
        :cell-style="cellStyle"
        :row-style="rowStyle"
        :style="tableStyle"
      >
        <el-table-column prop="name" label="文件名" width="400" />

        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="w-28 bg-slate-200 dark:bg-gray-600 rounded-full h-3 mr-2">
                <div
                  class="h-3 rounded-full transition-all duration-300"
                  :class="{
                    'bg-blue-500': row.status === 'uploading',
                    'bg-green-500': row.status === 'success',
                    'bg-red-500': row.status === 'error',
                  }"
                  :style="{ width: `${row.progress}%` }"
                ></div>
              </div>
              <span class="text-xs text-slate-600 dark:text-gray-300 font-semibold whitespace-nowrap">
                {{ row.status === 'success' ? '完成' : row.status === 'error' ? '失败' : `${row.progress}%` }}
              </span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                progressing: row.status === 'uploading',
                success: row.status === 'success',
                error: row.status === 'error',
              }"
            ></span>
            <span class="ml-2 text-sm">
              <span v-if="row.status === 'uploading'" class="text-blue-400">上传中</span>
              <span v-else-if="row.status === 'success'" class="text-green-400">已完成</span>
              <span v-else class="text-red-400">失败</span>
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <!-- 字幕转译任务 -->
  <div class="mb-8">
    <div
      class="bg-gradient-to-r from-white to-slate-50 dark:from-slate-800/90 dark:to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-200 dark:border-slate-600/50 shadow-2xl"
    >
      <!-- 标题栏 -->
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-bold text-slate-900 dark:text-white">{{ t('subtitleTranslation') }}</h2>
        <el-button
          type="primary"
          size="small"
          class="bg-blue-600 hover:bg-blue-700 border-blue-600"
          @click="fetchSubtitleTasks"
        >
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>

      <!-- 深色主题表格 -->
      <el-table
        :data="subtitleTasks"
        class="dark-table"
        :header-cell-style="headerCellStyle"
        :cell-style="cellStyle"
        :row-style="rowStyle"
        :style="tableStyle"
      >
        <!-- 文件名 -->
        <el-table-column prop="fileName" :label="t('filename')" width="400" />

        <!-- 🆕 总进度条（第二列） -->
        <el-table-column :label="t('totalProgress')" width="200">
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="w-28 bg-slate-200 dark:bg-gray-600 rounded-full h-3 mr-2">
                <div
                  class="h-3 rounded-full transition-all duration-300"
                  :class="{
                    'bg-blue-500': row.totalProgress < 100,
                    'bg-green-500': row.totalProgress === 100,
                  }"
                  :style="{ width: `${row.totalProgress}%` }"
                ></div>
              </div>
              <span class="text-xs text-slate-600 dark:text-gray-300 font-semibold whitespace-nowrap">{{ row.totalProgress.toFixed(1) }}%</span>
            </div>
          </template>
        </el-table-column>

        <!-- 字幕生成进度 -->
        <el-table-column :label="t('subtitleGeneration')" min-width="120">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.transcribe === 'Queued',
                progressing: row.transcribe === 'Running',
                success: row.transcribe === 'Completed',
                error: row.transcribe === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>
        <!-- 字幕优化进度 -->
        <el-table-column :label="t('subtitleOptimization')" min-width="120">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.optimize === 'Queued',
                progressing: row.optimize === 'Running',
                success: row.optimize === 'Completed',
                error: row.optimize === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>
        <!-- 翻译进度 -->
        <el-table-column :label="t('translationProgress')" min-width="120">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.translate === 'Queued',
                progressing: row.translate === 'Running',
                success: row.translate === 'Completed',
                error: row.translate === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>
        <!-- 操作 -->
        <el-table-column :label="t('operation')" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <el-dropdown
                trigger="click"
                @command="(cmd: 'retry' | 'delete') => handleCommand(row, cmd)"
              >
                <!-- More 图标，slot default 用 span 包一下 -->
                <span class="more-icon">
                  <el-icon><More /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-item command="retry">{{ t('retry') }}</el-dropdown-item>
                  <el-dropdown-item command="delete">{{ t('deleteTask') }}</el-dropdown-item>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <!-- 视频下载任务 -->
  <div class="mb-8">
    <div
      class="bg-gradient-to-r from-white to-slate-50 dark:from-slate-800/90 dark:to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-200 dark:border-slate-600/50 shadow-2xl"
    >
      <!-- 标题栏 -->
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-bold text-slate-900 dark:text-white">{{ t('videoDownload') }}</h2>
        <el-button
          type="primary"
          size="small"
          class="bg-blue-600 hover:bg-blue-700 border-blue-600"
          @click="fetchDownloadTasks"
        >
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>

      <!-- 深色主题表格 -->
      <el-table
        :data="downloadTasks"
        class="dark-table"
        :header-cell-style="headerCellStyle"
        :cell-style="cellStyle"
        :row-style="rowStyle"
        :style="tableStyle"
      >
        <!-- 文件名 -->
        <el-table-column prop="fileName" :label="t('filename')" width="400" />

        <!-- 🆕 总进度条 -->
        <el-table-column :label="t('totalProgress')" width="200">
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="w-28 bg-slate-200 dark:bg-gray-600 rounded-full h-3 mr-2">
                <div
                  class="h-3 rounded-full transition-all duration-300"
                  :class="{
                    'bg-blue-500': row.totalProgress < 100,
                    'bg-green-500': row.totalProgress === 100,
                  }"
                  :style="{ width: `${row.totalProgress}%` }"
                ></div>
              </div>
              <span class="text-xs text-slate-600 dark:text-gray-300 font-semibold whitespace-nowrap">{{ row.totalProgress.toFixed(1) }}%</span>
            </div>
          </template>
        </el-table-column>

        <!-- 视频下载进度 -->
        <el-table-column :label="t('videoDownloadProgress')" min-width="120">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.video === 'Queued',
                progressing: row.video === 'Running',
                success: row.video === 'Completed',
                error: row.video === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>
        <!-- 音频下载进度 -->
        <el-table-column :label="t('audioDownloadProgress')" min-width="120">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.audio === 'Queued',
                progressing: row.audio === 'Running',
                success: row.audio === 'Completed',
                error: row.audio === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>
        <!-- 拼接进度 -->
        <el-table-column :label="t('audioVideoMerge')" min-width="120">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.merge === 'Queued',
                progressing: row.merge === 'Running',
                success: row.merge === 'Completed',
                error: row.merge === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>
        <!-- 操作 -->
        <el-table-column :label="t('operation')" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <el-dropdown
                trigger="click"
                @command="(cmd: 'retry' | 'delete') => handleCommand(row, cmd)"
              >
                <!-- More 图标，slot default 用 span 包一下 -->
                <span class="more-icon">
                  <el-icon><More /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-item command="retry">{{ t('retry') }}</el-dropdown-item>
                  <el-dropdown-item command="delete">{{ t('deleteTask') }}</el-dropdown-item>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <!-- 视频摘要任务 -->
  <div class="mb-8">
    <div
      class="bg-gradient-to-r from-white to-slate-50 dark:from-slate-800/90 dark:to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-200 dark:border-slate-600/50 shadow-2xl"
    >
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-bold text-slate-900 dark:text-white">{{ t('videoSummary') }}</h2>
        <el-button
          size="small"
          @click="fetchSummaryTasks"
        >
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>

      <el-table
        :data="summaryTasks"
        class="dark-table"
        :header-cell-style="headerCellStyle"
        :cell-style="cellStyle"
        :row-style="rowStyle"
        :style="tableStyle"
      >
        <el-table-column prop="videoName" :label="t('videoName')" width="400" />

        <el-table-column :label="t('totalProgress')" width="200">
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="w-28 bg-slate-200 dark:bg-gray-600 rounded-full h-3 mr-2">
                <div
                  class="h-3 rounded-full transition-all duration-300"
                  :class="{
                    'bg-blue-500': row.totalProgress < 100,
                    'bg-green-500': row.totalProgress === 100,
                  }"
                  :style="{ width: `${row.totalProgress}%` }"
                ></div>
              </div>
              <span class="text-xs text-slate-600 dark:text-gray-300 font-semibold whitespace-nowrap">{{ row.totalProgress.toFixed(1) }}%</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="Caption" min-width="100">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.build === 'Queued',
                progressing: row.build === 'Running',
                success: row.build === 'Completed',
                error: row.build === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>

        <el-table-column label="OCR" min-width="100">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.extract === 'Queued',
                progressing: row.extract === 'Running',
                success: row.extract === 'Completed',
                error: row.extract === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>

        <el-table-column :label="t('summary')" min-width="100">
          <template #default="{ row }">
            <span
              class="status-dot"
              :class="{
                waiting: row.summarize === 'Queued',
                progressing: row.summarize === 'Running',
                success: row.summarize === 'Completed',
                error: row.summarize === 'Failed',
              }"
            ></span>
          </template>
        </el-table-column>

        <el-table-column :label="t('result')" min-width="200">
          <template #default="{ row }">
            <span v-if="row.resultPath" class="text-sm text-green-400">{{ t('completed') }}</span>
            <span v-else-if="row.errorMessage" class="text-xs text-red-400">{{ row.errorMessage.slice(0, 60) }}</span>
            <span v-else class="text-xs text-gray-500">-</span>
          </template>
        </el-table-column>

        <el-table-column :label="t('operation')" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <el-dropdown
                trigger="click"
                @command="(cmd: 'retry' | 'delete') => handleCommand(row, cmd)"
              >
                <span class="more-icon">
                  <el-icon><More /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-item command="retry">{{ t('retry') }}</el-dropdown-item>
                  <el-dropdown-item command="delete">{{ t('deleteTask') }}</el-dropdown-item>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

</template>

<style scoped>
:global(html.dark) .dark-table {
  background: #334155 !important;
}

:global(html.dark) .dark-table :deep(.el-table__header-wrapper) {
  background: #1e293b !important;
}

:global(html.dark) .dark-table :deep(.el-table__body-wrapper) {
  background: #334155 !important;
}

:global(html.dark) .dark-table :deep(.el-table__row) {
  background: #334155 !important;
}

:global(html.dark) .dark-table :deep(.el-table__row:hover > td) {
  background: #475569 !important;
}

/* 状态指示点样式 */
.status-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-right: 8px;
  border: 2px solid transparent;
}

.status-dot.waiting {
  background-color: #64748b;
  border-color: #64748b;
}

.status-dot.progressing {
  background-color: #3b82f6;
  border-color: #3b82f6;
  animation: pulse 2s infinite;
}

.status-dot.success {
  background-color: #10b981;
  border-color: #10b981;
}

.status-dot.error {
  background-color: #ef4444;
  border-color: #ef4444;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* 操作按钮样式 */
.more-icon {
  color: #64748b;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
}

.more-icon:hover {
  color: #1e293b;
  background: #f1f5f9;
}

:global(html.dark) .more-icon {
  color: #94a3b8;
}

:global(html.dark) .more-icon:hover {
  color: #e2e8f0;
  background: #475569;
}

/* 表格样式 */
.title-with-line {
  border-bottom: 1px dashed #d3d3d3; /* 轻灰色虚线 */
  padding-bottom: 0.5rem; /* 给下边框留点空隙 */
}

/* 操作按钮默认隐藏 */
.action-cell .more-icon {
  visibility: hidden;
  cursor: pointer;
}
/* 鼠标移到当前行时，显示图标 */
.el-table__row:hover .action-cell .more-icon {
  visibility: visible;
}

</style>
