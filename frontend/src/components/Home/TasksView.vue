<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from '@/composables/useNotification'
import { Refresh, More } from '@element-plus/icons-vue'
import { getCookie } from '@/composables/GetCSRFToken'
import { useI18n } from 'vue-i18n'

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

interface ExportTaskRow {
  id: string
  videoName: string
  subtitleType: string
  status: string
  progress: number
  outputFilename: string
  errorMessage: string
}

interface ExportTaskInfo {
  video_id: number
  video_name: string
  subtitle_type: 'raw' | 'translated' | 'both'
  status: string
  progress: number
  output_filename: string
  error_message: string
}

import { BACKEND } from '@/composables/ConfigAPI'
import { useUploadTasks } from '@/composables/useUploadTasks'

const { uploadTasks, clearFinished } = useUploadTasks()

const TASKS_URL = '/api/tasks/subtitle_generate/status'
const DOWNLOAD_STATUS_URL = '/api/stream_media/download_status'
const EXPORT_STATUS_URL = '/api/export/status'
const POLL_INTERVAL = 3_000

// i18n functionality
const { t } = useI18n()

const subtitleTasks = ref<TaskRow[]>([])
const downloadTasks = ref<DownloadTaskRow[]>([])
const exportTasks = ref<ExportTaskRow[]>([])
let timer_download: number | undefined
let timer_subtitle: number | undefined
let timer_export: number | undefined

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

async function fetchExportTasks() {
  try {
    const res = await fetch(`${BACKEND}${EXPORT_STATUS_URL}`, { credentials: 'include' })
    if (!res.ok) throw new Error(await res.text())

    const result = await res.json()
    if (!result.success) {
      throw new Error(result.message || '获取导出任务失败')
    }

    const raw = result.data as Record<string, ExportTaskInfo>

    exportTasks.value = Object.entries(raw).map(([id, info]) => ({
      id: id,
      videoName: info.video_name,
      subtitleType: getSubtitleTypeLabel(info.subtitle_type),
      status: info.status,
      progress: info.progress,
      outputFilename: info.output_filename,
      errorMessage: info.error_message,
    }))
  } catch (err) {
    ElMessage.error(`${t('exportTaskListFailed')}：${err}`)
  }
}

function getSubtitleTypeLabel(type: string): string {
  switch (type) {
    case 'raw':
      return t('originalSubtitle')
    case 'translated':
      return t('translatedSubtitle')
    case 'both':
      return t('bilingualSubtitle')
    default:
      return type
  }
}

function getStatusLabel(status: string): string {
  switch (status) {
    case 'Queued':
      return t('queued')
    case 'Running':
      return t('running')
    case 'Completed':
      return t('completed')
    case 'Failed':
      return t('failed')
    default:
      return status
  }
}
type Command = 'retry' | 'delete' | 'download'
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

// 导出任务重试／删除函数
async function retryExport(id: string) {
  try {
    const res = await fetch(`${BACKEND}/api/export/${id}/retry`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
    })
    if (!res.ok) throw new Error(await res.text())
    ElMessage.success(t('exportTaskRescheduled'))
    await fetchExportTasks()
  } catch (err: any) {
    ElMessage.error(`${t('retryFailed')}：${err.message}`)
  }
}

// 下载导出的视频文件
async function downloadExportedVideo(taskId: string, filename: string) {
  try {
    ElMessage.info(t('startingDownload'))

    const response = await fetch(`${BACKEND}/api/export/${taskId}/download`, {
      method: 'GET',
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`下载失败: ${response.status}`)
    }

    // 使用 Blob 和 createObjectURL 创建下载链接
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)

    // 创建临时下载链接
    const link = document.createElement('a')
    link.href = url
    link.download = filename || 'exported_video.mp4'
    link.style.display = 'none'

    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    // 清理 blob URL
    URL.revokeObjectURL(url)

    ElMessage.success(t('downloadCompleted'))
  } catch (err: any) {
    console.error('Download error:', err)
    ElMessage.error(`${t('downloadFailed')}：${err.message}`)
  }
}

async function deleteExport(id: string) {
  try {
    const res = await fetch(`${BACKEND}/api/export/${id}/delete`, {
      method: 'DELETE',
      credentials: 'include',
    })
    if (!res.ok) throw new Error(await res.text())
    ElMessage.success(t('exportTaskDeleted'))
    await fetchExportTasks()
  } catch (err: any) {
    ElMessage.error(`${t('deleteFailed')}：${err.message}`)
  }
}

function handleCommand(row: TaskRow | DownloadTaskRow | ExportTaskRow, command: Command): void {
  console.log('handleCommand → row:', row, 'command:', command)
  if (command === 'retry') {
    if ('bvid' in row) {
      retryDownload(row.id)
    } else if ('videoName' in row) {
      retryExport(row.id)
    } else {
      retrySubtitle(row.id)
    }
  } else if (command === 'download') {
    if ('videoName' in row) {
      downloadExportedVideo(row.id, row.outputFilename)
    }
  } else {
    if ('bvid' in row) {
      deleteDownload(row.id)
    } else if ('videoName' in row) {
      deleteExport(row.id)
    } else {
      deleteSubtitle(row.id)
    }
  }
}

onMounted(() => {
  fetchDownloadTasks()
  fetchSubtitleTasks()
  fetchExportTasks()
  timer_download = window.setInterval(fetchDownloadTasks, POLL_INTERVAL)
  timer_subtitle = window.setInterval(fetchSubtitleTasks, POLL_INTERVAL)
  timer_export = window.setInterval(fetchExportTasks, POLL_INTERVAL)
})

onBeforeUnmount(() => {
  clearInterval(timer_download)
  clearInterval(timer_subtitle)
  clearInterval(timer_export)
})
</script>

<template>
  <!-- 文件上传任务 -->
  <div v-if="uploadTasks.length" class="mb-8">
    <div
      class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-600/50 shadow-2xl"
    >
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-bold text-white">文件上传</h2>
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
        :header-cell-style="{ background: '#1e293b', color: '#e2e8f0', borderColor: '#475569' }"
        :cell-style="{ background: '#334155', color: '#e2e8f0', borderColor: '#475569' }"
        :row-style="{ background: '#334155' }"
        style="width: 100%; background: #334155"
      >
        <el-table-column prop="name" label="文件名" width="400" />

        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="w-28 bg-gray-600 rounded-full h-3 mr-2">
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
              <span class="text-xs text-gray-300 font-semibold whitespace-nowrap">
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
      class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-600/50 shadow-2xl"
    >
      <!-- 标题栏 -->
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-bold text-white">{{ t('subtitleTranslation') }}</h2>
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
        :header-cell-style="{ background: '#1e293b', color: '#e2e8f0', borderColor: '#475569' }"
        :cell-style="{ background: '#334155', color: '#e2e8f0', borderColor: '#475569' }"
        :row-style="{ background: '#334155' }"
        style="width: 100%; background: #334155"
      >
        <!-- 文件名 -->
        <el-table-column prop="fileName" :label="t('filename')" width="400" />

        <!-- 🆕 总进度条（第二列） -->
        <el-table-column :label="t('totalProgress')" width="200">
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="w-28 bg-gray-600 rounded-full h-3 mr-2">
                <div
                  class="h-3 rounded-full transition-all duration-300"
                  :class="{
                    'bg-blue-500': row.totalProgress < 100,
                    'bg-green-500': row.totalProgress === 100,
                  }"
                  :style="{ width: `${row.totalProgress}%` }"
                ></div>
              </div>
              <span class="text-xs text-gray-300 font-semibold whitespace-nowrap">{{ row.totalProgress.toFixed(1) }}%</span>
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
      class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-600/50 shadow-2xl"
    >
      <!-- 标题栏 -->
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-bold text-white">{{ t('videoDownload') }}</h2>
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
        :header-cell-style="{ background: '#1e293b', color: '#e2e8f0', borderColor: '#475569' }"
        :cell-style="{ background: '#334155', color: '#e2e8f0', borderColor: '#475569' }"
        :row-style="{ background: '#334155' }"
        style="width: 100%; background: #334155"
      >
        <!-- 文件名 -->
        <el-table-column prop="fileName" :label="t('filename')" width="400" />

        <!-- 🆕 总进度条 -->
        <el-table-column :label="t('totalProgress')" width="200">
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="w-28 bg-gray-600 rounded-full h-3 mr-2">
                <div
                  class="h-3 rounded-full transition-all duration-300"
                  :class="{
                    'bg-blue-500': row.totalProgress < 100,
                    'bg-green-500': row.totalProgress === 100,
                  }"
                  :style="{ width: `${row.totalProgress}%` }"
                ></div>
              </div>
              <span class="text-xs text-gray-300 font-semibold whitespace-nowrap">{{ row.totalProgress.toFixed(1) }}%</span>
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
        <el-table-column label="操作" width="80" align="center" fixed="right">
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

  <!-- 视频导出任务 -->
  <div class="mb-8">
    <div
      class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl p-6 border border-slate-600/50 shadow-2xl"
    >
      <!-- 标题栏 -->
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-xl font-bold text-white">{{ t('videoExport') }}</h2>
        <el-button
          type="primary"
          size="small"
          class="bg-blue-600 hover:bg-blue-700 border-blue-600"
          @click="fetchExportTasks"
        >
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>

      <!-- 深色主题表格 -->
      <el-table
        :data="exportTasks"
        class="dark-table"
        :header-cell-style="{ background: '#1e293b', color: '#e2e8f0', borderColor: '#475569' }"
        :cell-style="{ background: '#334155', color: '#e2e8f0', borderColor: '#475569' }"
        :row-style="{ background: '#334155' }"
        style="width: 100%; background: #334155"
      >
        <!-- 视频名称 -->
        <el-table-column prop="videoName" :label="t('videoName')" width="400" />

        <!-- 🆕 总进度（第二列） -->
        <el-table-column :label="t('totalProgress')" width="200">
          <template #default="{ row }">
            <div class="flex items-center">
              <div class="w-28 bg-gray-600 rounded-full h-3 mr-2">
                <div
                  class="h-3 rounded-full transition-all duration-300"
                  :class="{
                    'bg-blue-500': row.progress < 100,
                    'bg-green-500': row.progress === 100,
                  }"
                  :style="{ width: `${row.progress}%` }"
                ></div>
              </div>
              <span class="text-xs text-gray-300 font-semibold whitespace-nowrap">{{ row.progress }}%</span>
            </div>
          </template>
        </el-table-column>

        <!-- 字幕类型 -->
        <el-table-column
          prop="subtitleType"
          :label="t('subtitleType')"
          min-width="120"
        />

        <!-- 导出状态 -->
        <el-table-column :label="t('exportStatus')" min-width="150">
          <template #default="{ row }">
            <div class="flex items-center">
              <span
                class="status-dot"
                :class="{
                  waiting: row.status === 'Queued',
                  progressing: row.status === 'Running',
                  success: row.status === 'Completed',
                  error: row.status === 'Failed',
                }"
              ></span>
              <span class="ml-2 text-sm">
                <span v-if="row.status === 'Failed'" class="text-red-400">任务失败</span>
                <span v-else-if="row.status === 'Running'" class="text-blue-400">进行中</span>
                <span v-else-if="row.status === 'Completed'" class="text-green-400">已完成</span>
                <span v-else>{{ getStatusLabel(row.status) }}</span>
              </span>
            </div>
          </template>
        </el-table-column>
        <!-- 输出文件 -->
        <el-table-column :label="t('outputFile')" min-width="180">
          <template #default="{ row }">
            <span v-if="row.outputFilename" class="text-sm text-gray-300">{{
              row.outputFilename
            }}</span>
            <span v-else-if="row.errorMessage" class="text-xs text-red-400">{{
              row.errorMessage
            }}</span>
            <span v-else class="text-xs text-gray-500">-</span>
          </template>
        </el-table-column>
        <!-- 操作 -->
        <el-table-column label="操作" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <el-dropdown
                trigger="click"
                @command="(cmd: 'retry' | 'delete' | 'download') => handleCommand(row, cmd)"
              >
                <!-- More 图标，slot default 用 span 包一下 -->
                <span class="more-icon">
                  <el-icon><More /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-item
                    v-if="row.status === 'Completed' && row.outputFilename"
                    command="download"
                    class="text-green-400 hover:text-green-300"
                  >
                    {{ t('download') }}
                  </el-dropdown-item>
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
/* 深色主题表格样式 */
.dark-table {
  background: #334155 !important;
}

.dark-table :deep(.el-table__header-wrapper) {
  background: #1e293b !important;
}

.dark-table :deep(.el-table__body-wrapper) {
  background: #334155 !important;
}

.dark-table :deep(.el-table__row) {
  background: #334155 !important;
}

.dark-table :deep(.el-table__row:hover > td) {
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
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
}

.more-icon:hover {
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

/* 下载选项样式 */
:deep(.el-dropdown-item.text-green-400) {
  color: #22c55e !important;
}
:deep(.el-dropdown-item.text-green-400:hover) {
  color: #16a34a !important;
  background-color: rgba(34, 197, 94, 0.1) !important;
}
</style>
