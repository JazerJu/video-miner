<script setup lang="ts">
import { More, EditPen } from '@element-plus/icons-vue'
import { Clock3, Play, Upload, Headphones, Link, SquarePen } from 'lucide-vue-next'
import { PictureFilled } from '@element-plus/icons-vue'
import { computed, ref, nextTick } from 'vue'
import type { Video } from '@/types/media'
import { getCSRFToken } from '@/composables/GetCSRFToken'
import { useNotification } from '@/composables/useNotification'
import { BACKEND } from '@/composables/ConfigAPI'

const props = defineProps<{
  video: Video
  view: 'grid' | 'list'
  batchMode?: boolean
  checked?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit-thumbnail', video: Video): void
  (e: 'generate-subtitle', video: Video): void
  (e: 'delete', video: Video): void
  (e: 'move-category', video: Video): void
  (e: 'update:checked', v: boolean): void
  (e: 'rename-video', video: Video, newName: string): void
  (e: 'update-props', video: Video): void
}>()

const { success: successNotify, error: errorNotify, warning: warningNotify } = useNotification()

const FALLBACK_IMG =
  'https://pic.chaopx.com/chao_water_pic/23/03/03/e78a5cf45f9ebc92411a8f9531975dec.jpg'

const watchUrl = computed(() => `watch/${encodeURIComponent(props.video.url)}`)
const filename = props.video.thumbnail_url || props.video.thumbnail || ''
const thumbnailUrl = computed(() =>
  filename ? `${BACKEND}/media/thumbnail/${encodeURIComponent(filename)}` : ''
)
const durationLabel = computed(() => props.video.length || props.video.video_length || '')
const categoryLabel = computed(() => props.video.categoryName || '未归档')
const sourceUrlValue = computed(() => props.video.sourceUrl || props.video.source_url || '')

function inferSourceFromUrl(url?: string) {
  if (!url) return ''
  const normalized = url.toLowerCase()
  if (normalized.includes('youtube.com') || normalized.includes('youtu.be')) return 'youtube'
  if (normalized.includes('bilibili.com') || normalized.includes('b23.tv') || normalized.includes('bilivideo.com')) return 'bilibili'
  if (normalized.includes('podcasts.apple.com') || normalized.includes('apple.com') || normalized.includes('rss')) return 'podcast'
  return ''
}

const resolvedSource = computed(() => {
  const explicit = props.video.videoSource || props.video.video_source || ''
  return explicit || inferSourceFromUrl(sourceUrlValue.value) || 'upload'
})

const sourceLabel = computed(() => {
  const source = resolvedSource.value
  switch (source) {
    case 'bilibili':
      return 'Bilibili'
    case 'youtube':
      return 'YouTube'
    case 'podcast':
      return 'Podcast'
    default:
      return 'Upload'
  }
})
const sourceBadgeClass = computed(() => {
  const source = resolvedSource.value
  switch (source) {
    case 'bilibili':
      return 'border-sky-400/35 bg-sky-50 text-sky-700 dark:border-sky-400/25 dark:bg-sky-500/12 dark:text-sky-100'
    case 'youtube':
      return 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/25 dark:bg-rose-500/12 dark:text-rose-100'
    case 'podcast':
      return 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-300/25 dark:bg-amber-500/12 dark:text-amber-100'
    default:
      return 'border-slate-200 bg-white text-slate-900 dark:border-white/12 dark:bg-white/[0.06] dark:text-slate-100'
  }
})

function formatAbsoluteDateTime(value?: string) {
  if (!value) return '暂无记录'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatAccessLabel(value?: string) {
  if (!value) return '暂无访问'

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '最近访问'

  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOfTarget = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate())
  const dayDiff = Math.floor((startOfToday.getTime() - startOfTarget.getTime()) / 86400000)

  if (dayDiff <= 0) return '今天访问'
  if (dayDiff === 1) return '昨天访问'
  if (dayDiff < 7) return `${dayDiff}天前访问`
  if (dayDiff < 30) return `${Math.floor(dayDiff / 7)}周前访问`
  if (dayDiff < 365) return `${Math.floor(dayDiff / 30)}个月前访问`
  return `${Math.floor(dayDiff / 365)}年前访问`
}

const accessLabel = computed(() => formatAccessLabel(props.video.last_accessed_at))

function parseDurationToSeconds(duration?: string) {
  if (!duration) return 0
  const parts = duration.split(':').map(part => Number(part))
  if (parts.some(part => Number.isNaN(part))) return 0
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 1) return parts[0]
  return 0
}

const playbackProgress = computed(() => {
  const played = props.video.last_played_time || 0
  const durationSeconds = props.video.video_length_seconds || parseDurationToSeconds(durationLabel.value)
  if (played <= 0 || durationSeconds <= 0) return 0
  return Math.min(Math.max(played / durationSeconds, 0), 1)
})

const hasPlaybackProgress = computed(() => playbackProgress.value > 0.01)

const visibleTags = computed(() => (props.video.tags || []).slice(0, 3))
const hiddenTagCount = computed(() => Math.max((props.video.tags?.length || 0) - visibleTags.value.length, 0))

const TAG_PALETTE = [
  { bg: 'rgba(245, 158, 11, 0.92)', border: 'rgba(251, 191, 36, 0.95)' },
  { bg: 'rgba(236, 72, 153, 0.92)', border: 'rgba(244, 114, 182, 0.95)' },
  { bg: 'rgba(59, 130, 246, 0.92)', border: 'rgba(96, 165, 250, 0.95)' },
  { bg: 'rgba(16, 185, 129, 0.92)', border: 'rgba(52, 211, 153, 0.95)' },
  { bg: 'rgba(168, 85, 247, 0.92)', border: 'rgba(192, 132, 252, 0.95)' },
  { bg: 'rgba(239, 68, 68, 0.92)', border: 'rgba(248, 113, 113, 0.95)' },
]

function getTagStyle(tag: string) {
  const hash = [...tag].reduce((acc, char) => acc + char.charCodeAt(0), 0)
  const palette = TAG_PALETTE[hash % TAG_PALETTE.length]
  return {
    backgroundColor: palette.bg,
    borderColor: palette.border,
  }
}

// ── Inline rename ──────────────────────────────────────────────
const isEditing = ref(false)
const editingName = ref('')
const inputRef = ref<HTMLInputElement>()

const startEditing = async () => {
  isEditing.value = true
  editingName.value = props.video.name
  await nextTick()
  inputRef.value?.focus()
  inputRef.value?.select()
}

const saveEdit = async () => {
  const newName = editingName.value.trim()
  if (!newName) { warningNotify('名称不能为空'); return }
  if (newName === props.video.name) { isEditing.value = false; return }
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/${props.video.id}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      credentials: 'include',
      body: JSON.stringify({ videoId: props.video.id, newName }),
    })
    const result = await response.json()
    if (result.success) {
      emit('rename-video', props.video, newName)
      isEditing.value = false
      successNotify('重命名成功')
    } else {
      errorNotify(result.message || '重命名失败')
    }
  } catch {
    errorNotify('网络错误，请重试')
  }
}

const cancelEdit = () => { isEditing.value = false; editingName.value = '' }

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') saveEdit()
  else if (event.key === 'Escape') cancelEdit()
}

// ── Video properties dialog ────────────────────────────────────
const showPropsDialog = ref(false)
const propsForm = ref({ rawLang: '', videoSource: '', sourceUrl: '' })
const propsSaving = ref(false)

const openPropsDialog = () => {
  propsForm.value = {
    rawLang: props.video.rawLang || props.video.raw_lang || '',
    videoSource: props.video.videoSource || props.video.video_source || '',
    sourceUrl: props.video.sourceUrl || props.video.source_url || '',
  }
  showPropsDialog.value = true
}

const saveProps = async () => {
  propsSaving.value = true
  try {
    const csrf = await getCSRFToken()
    const res = await fetch(`${BACKEND}/api/videos/${props.video.id}/props`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      credentials: 'include',
      body: JSON.stringify({
        raw_lang: propsForm.value.rawLang,
        video_source: propsForm.value.videoSource,
        source_url: propsForm.value.sourceUrl,
      }),
    })
    const result = await res.json()
    if (result.success) {
      props.video.rawLang = result.raw_lang
      props.video.videoSource = result.video_source
      props.video.sourceUrl = result.source_url
      emit('update-props', props.video)
      showPropsDialog.value = false
      successNotify('属性已保存')
    } else {
      errorNotify(result.error || '保存失败')
    }
  } catch {
    errorNotify('网络错误，保存失败')
  } finally {
    propsSaving.value = false
  }
}

const openEditor = () => {
  window.location.href = '/editor/' + encodeURIComponent(props.video.url)
}

const modelChecked = computed({
  get: () => props.checked ?? false,
  set: (v) => emit('update:checked', v),
})

const PLATFORM_OPTIONS = [
  { value: 'bilibili', label: 'Bilibili' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'podcast', label: 'Podcast' },
  { value: 'upload', label: 'Upload' },
]

const LANG_OPTIONS = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'jp', label: '日本語' },
  { value: 'de', label: 'Deutsch' },
]
</script>

<template>
  <!-- ───────────── GRID STYLE ───────────── -->
  <div
    v-if="view === 'grid'"
    class="video-card-hover group relative overflow-hidden rounded-[22px] border border-slate-200 bg-white shadow-[0_18px_40px_rgba(2,6,23,0.22)] transition-all duration-300 hover:-translate-y-1 hover:border-slate-300 hover:shadow-[0_22px_52px_rgba(2,6,23,0.3)] dark:border-white/8 dark:bg-[linear-gradient(180deg,rgba(30,41,59,0.96),rgba(15,23,42,0.96))] dark:hover:border-white/14"
    :class="checked ? 'border-[rgb(34,124,46)] border-2' : ''"
  >
    <el-checkbox
      v-model="modelChecked"
      :label="''"
      class="video-select !absolute top-1.5 left-1.5 z-30 transition-opacity opacity-0 group-hover:opacity-100"
      :class="batchMode ? '!opacity-100' : ''"
    />
    <div class="relative aspect-video overflow-hidden bg-slate-950">
      <img
        :src="thumbnailUrl || FALLBACK_IMG"
        class="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
        :alt="video.name"
      />
      <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />

      <div v-if="hasPlaybackProgress" class="absolute inset-x-0 bottom-0 z-10 h-1 bg-slate-200 dark:bg-slate-950/45">
        <div
          class="h-full rounded-r-full bg-[linear-gradient(90deg,#7dd3fc,#5eead4,#60a5fa)] shadow-[0_0_10px_rgba(125,211,252,0.45)]"
          :style="{ width: `${playbackProgress * 100}%` }"
        />
      </div>

      <div class="absolute left-3 top-3 inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em]" :class="sourceBadgeClass">
        {{ sourceLabel }}
      </div>

      <div v-if="durationLabel" class="absolute bottom-3 right-3 rounded-md bg-black/72 px-2.5 py-1 text-xs font-semibold text-white/95 shadow-lg dark:text-white">
        {{ durationLabel }}
      </div>

      <div v-if="visibleTags.length" class="absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-5.5rem)] flex-wrap items-center gap-1.5">
        <span
          v-for="tag in visibleTags"
          :key="tag"
          class="inline-flex max-w-full items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold text-white/95 shadow-[0_8px_20px_rgba(15,23,42,0.24)] backdrop-blur-sm dark:text-white"
          :style="getTagStyle(tag)"
        >
          <span class="truncate">{{ tag }}</span>
        </span>
        <span
          v-if="hiddenTagCount > 0"
          class="inline-flex items-center rounded-full border border-slate-300 bg-black/55 px-2.5 py-1 text-[11px] font-semibold text-white/90 backdrop-blur-sm dark:border-white/18"
        >
          +{{ hiddenTagCount }}
        </span>
      </div>

      <div class="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-300 group-hover:opacity-100">
        <a
          :href="watchUrl"
          class="flex h-12 w-12 items-center justify-center rounded-full border border-slate-300 bg-black/55 text-white/95 shadow-lg backdrop-blur-md transition hover:scale-105 hover:bg-black/72 dark:border-white/18 dark:text-white"
        >
          <Play :size="20" class="ml-0.5" />
        </a>
      </div>

      <div class="absolute right-3 top-3 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
        <el-dropdown trigger="click">
          <button class="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-black/45 text-white/85 backdrop-blur-md transition hover:bg-black/70 dark:border-white/10 dark:hover:text-white">
            <el-icon class="text-lg"><More /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="emit('edit-thumbnail', video)">
                <el-icon><PictureFilled /></el-icon>
                <span style="margin-left: 4px">更换预览图</span>
              </el-dropdown-item>
              <el-dropdown-item @click="openEditor">
                <el-icon class="mr-2"><EditPen /></el-icon> 编辑字幕
              </el-dropdown-item>
              <el-dropdown-item @click="startEditing" divided>
                <SquarePen class="w-4 h-4 mr-2" /> 重命名
              </el-dropdown-item>
              <el-dropdown-item @click="openPropsDialog">
                <Link class="w-4 h-4 mr-2" /> 视频属性
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <div class="p-4">
      <div v-if="!isEditing" class="flex items-start gap-3">
        <el-tooltip :content="video.name" placement="top">
          <h3 class="flex-1 text-[1.05rem] font-semibold leading-6 text-slate-900 line-clamp-2 dark:text-white">
            <a :href="watchUrl" class="no-underline text-inherit transition-colors hover:text-cyan-600 dark:hover:text-cyan-200">
              {{ video.name }}
            </a>
          </h3>
        </el-tooltip>

        <el-popover placement="top-end" :width="280" trigger="hover">
          <template #reference>
            <button class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-600 transition hover:border-slate-300 hover:bg-slate-100 hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:border-white/18 dark:hover:bg-white/10 dark:hover:text-white">
              <Clock3 class="h-4 w-4" />
            </button>
          </template>

          <div class="space-y-3 text-sm text-slate-800">
            <div class="flex items-start justify-between gap-4">
              <span class="text-slate-500">最后访问</span>
              <span class="text-right font-medium text-slate-800">{{ formatAbsoluteDateTime(video.last_accessed_at) }}</span>
            </div>
            <div class="flex items-start justify-between gap-4">
              <span class="text-slate-500">入库时间</span>
              <span class="text-right font-medium text-slate-800">{{ formatAbsoluteDateTime(video.added_at || video.file_created_time) }}</span>
            </div>
            <div class="flex items-start justify-between gap-4">
              <span class="text-slate-500">内容更新</span>
              <span class="text-right font-medium text-slate-800">{{ formatAbsoluteDateTime(video.content_updated_at) }}</span>
            </div>
          </div>
        </el-popover>
      </div>
      <div v-else class="mb-2 flex items-center gap-2">
        <input
          ref="inputRef"
          v-model="editingName"
          class="flex-1 rounded-lg border border-slate-300 bg-slate-100 px-3 py-2 font-semibold text-slate-900 backdrop-blur-sm placeholder-slate-500 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-400 dark:border-white/15 dark:bg-white/10 dark:text-white dark:placeholder-white/50"
          @keydown="handleKeydown"
          @blur="saveEdit"
        />
      </div>

      <div class="mt-3 flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
        <span class="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-800 dark:border-white/10 dark:bg-white/5 dark:text-slate-200">
          {{ categoryLabel }}
        </span>
        <span class="text-slate-500">•</span>
        <span class="truncate text-slate-500 dark:text-slate-400">{{ accessLabel }}</span>
      </div>
    </div>
  </div>

  <!-- ───────────── LIST STYLE ───────────── -->
  <div
    v-else
    class="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3 transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700/50 dark:bg-slate-900/45 dark:hover:border-slate-600/70 dark:hover:bg-slate-900/72"
  >
    <div class="flex items-center gap-4">
      <div class="relative overflow-hidden rounded-xl">
        <img
          :src="thumbnailUrl || FALLBACK_IMG"
          class="h-16 w-28 object-cover"
          :alt="video.name"
        />
        <div v-if="hasPlaybackProgress" class="absolute inset-x-0 bottom-0 z-10 h-1 bg-slate-200 dark:bg-slate-950/40">
          <div
            class="h-full rounded-r-full bg-[linear-gradient(90deg,#7dd3fc,#5eead4,#60a5fa)] shadow-[0_0_8px_rgba(125,211,252,0.4)]"
            :style="{ width: `${playbackProgress * 100}%` }"
          />
        </div>
        <div
          class="absolute inset-0 flex items-center justify-center bg-black/35 opacity-0 transition-opacity hover:opacity-100"
        >
          <a :href="watchUrl">
            <span class="flex h-9 w-9 items-center justify-center rounded-full border border-slate-300 bg-black/55 text-white/95 backdrop-blur-md dark:border-white/18 dark:text-white">
              <Play :size="16" class="ml-0.5" />
            </span>
          </a>
        </div>
        <div v-if="durationLabel" class="absolute bottom-2 right-2 rounded-md bg-black/72 px-2 py-0.5 text-[11px] font-semibold text-white/95 dark:text-white">
          {{ durationLabel }}
        </div>
      </div>

      <div class="min-w-0">
        <div v-if="!isEditing" class="flex items-center gap-2">
          <el-tooltip :content="video.name" placement="top">
            <a :href="watchUrl" class="line-clamp-1 font-medium text-slate-900 no-underline hover:text-cyan-600 dark:text-white dark:hover:text-cyan-200">
              {{ video.name }}
            </a>
          </el-tooltip>
        </div>
        <div v-else class="flex items-center gap-2">
          <input
            ref="inputRef"
            v-model="editingName"
            class="rounded border border-cyan-300/40 bg-white px-2 py-1 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            @keydown="handleKeydown"
            @blur="saveEdit"
          />
        </div>
        <div class="mt-1 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <span class="rounded-full border px-2 py-0.5 text-[11px]" :class="sourceBadgeClass">{{ sourceLabel }}</span>
          <span>•</span>
          <span>{{ categoryLabel }}</span>
          <span>•</span>
          <span>{{ accessLabel }}</span>
        </div>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <el-popover placement="top-end" :width="280" trigger="hover">
        <template #reference>
          <button class="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-slate-100 text-slate-600 transition hover:border-slate-400 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300 dark:hover:border-slate-500 dark:hover:text-white">
            <Clock3 class="h-4 w-4" />
          </button>
        </template>

        <div class="space-y-3 text-sm text-slate-800">
          <div class="flex items-start justify-between gap-4">
            <span class="text-slate-500">最后访问</span>
            <span class="text-right font-medium text-slate-800">{{ formatAbsoluteDateTime(video.last_accessed_at) }}</span>
          </div>
          <div class="flex items-start justify-between gap-4">
            <span class="text-slate-500">入库时间</span>
            <span class="text-right font-medium text-slate-800">{{ formatAbsoluteDateTime(video.added_at || video.file_created_time) }}</span>
          </div>
          <div class="flex items-start justify-between gap-4">
            <span class="text-slate-500">内容更新</span>
            <span class="text-right font-medium text-slate-800">{{ formatAbsoluteDateTime(video.content_updated_at) }}</span>
          </div>
        </div>
      </el-popover>

      <el-dropdown trigger="click">
        <el-button circle class="!w-9 !h-9 !border-slate-200 !bg-slate-100 !text-slate-800 hover:!border-slate-400 hover:!bg-slate-200 dark:!border-slate-700 dark:!bg-slate-800/80 dark:!text-slate-200 dark:hover:!border-slate-500 dark:hover:!bg-slate-700">
          <el-icon><More /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="emit('edit-thumbnail', video)">
              <el-icon class="mr-2"><PictureFilled /></el-icon> 更换预览图
            </el-dropdown-item>
            <el-dropdown-item @click="openEditor">
              <el-icon class="mr-2"><EditPen /></el-icon> 编辑字幕
            </el-dropdown-item>
            <el-dropdown-item @click="startEditing" divided>
              <SquarePen class="w-4 h-4 mr-2" /> 重命名
            </el-dropdown-item>
            <el-dropdown-item @click="openPropsDialog">
              <Link class="w-4 h-4 mr-2" /> 视频属性
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>

  <!-- ───────────── Video Properties Dialog ───────────── -->
  <el-dialog
    v-model="showPropsDialog"
    title="视频属性"
    width="420px"
    class="video-props-dialog-shell"
    @close="showPropsDialog = false"
  >
    <div class="space-y-4 rounded-[20px] bg-slate-50 p-4 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.84),rgba(17,24,39,0.78))]">
      <div class="space-y-2">
        <label class="mb-2 block text-sm font-medium text-slate-800 dark:text-slate-200">原始语言</label>
        <el-select
          v-model="propsForm.rawLang"
          placeholder="不设置"
          clearable
          class="w-full"
          popper-class="video-props-select-popper"
          :teleported="false"
        >
          <el-option
            v-for="opt in LANG_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>

      <div class="border-t border-slate-200 pt-4 dark:border-white/8">
        <label class="mb-3 block text-sm font-medium text-slate-800 dark:text-slate-200">源平台</label>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="p in PLATFORM_OPTIONS"
            :key="p.value"
            @click="propsForm.videoSource = propsForm.videoSource === p.value ? '' : p.value"
            :class="[
              'flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm transition-all',
              propsForm.videoSource === p.value
                ? 'border-cyan-300/35 bg-cyan-400/14 text-cyan-600 dark:text-cyan-100 font-medium shadow-[0_10px_24px_rgba(34,211,238,0.12)]'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-100 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-300 dark:hover:border-white/20 dark:hover:bg-white/[0.07]',
            ]"
          >
            <!-- Bilibili icon -->
            <svg v-if="p.value === 'bilibili'" class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M17.813 4.653h.854c1.51.054 2.769.578 3.773 1.574 1.004.995 1.524 2.249 1.56 3.76v7.36c-.036 1.51-.556 2.769-1.56 3.773s-2.262 1.524-3.773 1.56H5.333c-1.51-.036-2.769-.556-3.773-1.56S.036 18.858 0 17.347v-7.36c.036-1.511.556-2.765 1.56-3.76 1.004-.996 2.262-1.52 3.773-1.574h.774l-1.174-1.12a1.234 1.234 0 0 1 0-1.773 1.234 1.234 0 0 1 1.773 0l2.88 2.76h4.107l2.88-2.76a1.234 1.234 0 0 1 1.773 0 1.234 1.234 0 0 1 0 1.773zM5.333 7.24c-.853.036-1.548.32-2.08.853-.53.533-.808 1.227-.853 2.08v7.013c.045.853.322 1.544.853 2.08.532.533 1.227.81 2.08.853h13.334c.853-.043 1.544-.32 2.08-.853.535-.536.81-1.227.853-2.08V10.173c-.043-.853-.318-1.547-.853-2.08-.536-.533-1.227-.817-2.08-.853zM9.2 10.853v4.48c0 .32-.11.59-.333.8a1.106 1.106 0 0 1-.8.32 1.106 1.106 0 0 1-.8-.32 1.085 1.085 0 0 1-.333-.8v-4.48c0-.32.11-.59.333-.8.222-.213.48-.32.8-.32.32 0 .578.107.8.32.222.21.333.48.333.8zm7.466 0v4.48c0 .32-.11.59-.333.8a1.106 1.106 0 0 1-.8.32 1.106 1.106 0 0 1-.8-.32 1.085 1.085 0 0 1-.333-.8v-4.48c0-.32.11-.59.333-.8.222-.213.48-.32.8-.32.32 0 .578.107.8.32.222.21.333.48.333.8z"/>
            </svg>
            <!-- YouTube icon -->
            <svg v-else-if="p.value === 'youtube'" class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
            </svg>
            <!-- Podcast icon -->
            <Headphones v-else-if="p.value === 'podcast'" class="w-4 h-4" />
            <!-- Upload icon -->
            <Upload v-else class="w-4 h-4" />
            {{ p.label }}
          </button>
        </div>
      </div>

      <div class="border-t border-slate-200 pt-4 dark:border-white/8">
        <label class="mb-2 block text-sm font-medium text-slate-800 dark:text-slate-200">源链接</label>
        <el-input
          v-model="propsForm.sourceUrl"
          placeholder="https://..."
          clearable
        />
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-3">
        <button
          class="inline-flex h-10 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm font-medium text-slate-800 transition hover:border-slate-300 hover:bg-slate-100 dark:border-white/12 dark:bg-white/[0.04] dark:text-slate-200 dark:hover:border-white/20 dark:hover:bg-white/[0.08]"
          @click="showPropsDialog = false"
        >
          取消
        </button>
        <button
          class="inline-flex h-10 items-center justify-center rounded-xl border border-cyan-400/20 bg-[linear-gradient(135deg,rgba(34,211,238,0.24),rgba(59,130,246,0.24))] px-4 text-sm font-semibold text-cyan-600 transition hover:border-cyan-300/35 hover:shadow-[0_12px_28px_rgba(34,211,238,0.16)] disabled:cursor-not-allowed disabled:opacity-65 dark:text-cyan-50"
          :disabled="propsSaving"
          @click="saveProps"
        >
          {{ propsSaving ? '保存中...' : '保存' }}
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
@reference "../../assets/tailwind.css";

.video-card-hover:hover {
  @apply transition-shadow;
}

.video-select {
  margin: 0 !important;
  padding: 0 !important;
  height: 20px !important;
  background: transparent;
}

:deep(.video-select .el-checkbox__label) {
  display: none;
}

:deep(.video-select .el-checkbox__input) {
  width: 20px;
  height: 20px;
}

:deep(.video-select .el-checkbox__inner) {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(15, 23, 42, 0.35);
  border-radius: 4px;
  background-color: rgba(255, 255, 255, 0.92);
  transition: all 0.2s ease;
}

:global(html.dark) :deep(.video-select .el-checkbox__inner) {
  border: 2px solid rgba(255, 255, 255, 0.6);
  background-color: rgba(0, 0, 0, 0.5);
}

:deep(.video-select .el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: rgb(34, 124, 46);
  border-color: rgb(34, 124, 46);
}

:deep(.video-select .el-checkbox__input.is-checked .el-checkbox__inner::after) {
  border-width: 0 2px 2px 0;
  left: 6px;
  top: 2px;
  width: 4px;
  height: 8px;
}

</style>

<style>
.el-dialog.video-props-dialog-shell,
.video-props-dialog-shell .el-dialog {
  overflow: hidden;
  border: 1px solid rgba(203, 213, 225, 0.9);
  border-radius: 22px;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.08), transparent 38%),
    linear-gradient(180deg, #ffffff, #f8fafc 52%, #f1f5f9);
  box-shadow: 0 24px 56px rgba(15, 23, 42, 0.16);
}

html.dark .el-dialog.video-props-dialog-shell,
html.dark .video-props-dialog-shell .el-dialog {
  border: 1px solid rgba(125, 211, 252, 0.1);
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.07), transparent 38%),
    linear-gradient(180deg, #111827, #0f172a 52%, #020617);
  box-shadow: 0 24px 56px rgba(2, 6, 23, 0.44);
}

.el-dialog.video-props-dialog-shell .el-dialog__header,
.el-dialog.video-props-dialog-shell .el-dialog__body,
.el-dialog.video-props-dialog-shell .el-dialog__footer,
.video-props-dialog-shell .el-dialog__header,
.video-props-dialog-shell .el-dialog__body,
.video-props-dialog-shell .el-dialog__footer {
  background: transparent;
}

.el-dialog.video-props-dialog-shell .el-dialog__header,
.video-props-dialog-shell .el-dialog__header {
  margin: 0;
  padding: 18px 18px 6px;
}

.el-dialog.video-props-dialog-shell .el-dialog__title,
.video-props-dialog-shell .el-dialog__title {
  color: #0f172a;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

html.dark .el-dialog.video-props-dialog-shell .el-dialog__title,
html.dark .video-props-dialog-shell .el-dialog__title {
  color: #f8fafc;
}

.el-dialog.video-props-dialog-shell .el-dialog__headerbtn .el-dialog__close,
.video-props-dialog-shell .el-dialog__headerbtn .el-dialog__close {
  color: rgba(71, 85, 105, 0.78);
}

html.dark .el-dialog.video-props-dialog-shell .el-dialog__headerbtn .el-dialog__close,
html.dark .video-props-dialog-shell .el-dialog__headerbtn .el-dialog__close {
  color: rgba(226, 232, 240, 0.78);
}

.el-dialog.video-props-dialog-shell .el-dialog__body,
.video-props-dialog-shell .el-dialog__body {
  padding: 10px 18px 14px;
}

.el-dialog.video-props-dialog-shell .el-dialog__footer,
.video-props-dialog-shell .el-dialog__footer {
  padding: 0 18px 18px;
}

.el-dialog.video-props-dialog-shell .el-input__wrapper,
.el-dialog.video-props-dialog-shell .el-select__wrapper,
.video-props-dialog-shell .el-input__wrapper,
.video-props-dialog-shell .el-select__wrapper {
  border: 1px solid rgba(203, 213, 225, 0.95);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: inset 0 1px 0 rgba(15, 23, 42, 0.03);
}

html.dark .el-dialog.video-props-dialog-shell .el-input__wrapper,
html.dark .el-dialog.video-props-dialog-shell .el-select__wrapper,
html.dark .video-props-dialog-shell .el-input__wrapper,
html.dark .video-props-dialog-shell .el-select__wrapper {
  border: 1px solid rgba(125, 211, 252, 0.12);
  background: rgba(15, 23, 42, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.el-dialog.video-props-dialog-shell .el-input__wrapper.is-focus,
.el-dialog.video-props-dialog-shell .el-select__wrapper.is-focused,
.video-props-dialog-shell .el-input__wrapper.is-focus,
.video-props-dialog-shell .el-select__wrapper.is-focused {
  box-shadow: 0 0 0 1px rgba(103, 232, 249, 0.28);
  border-color: rgba(103, 232, 249, 0.28);
}

.el-dialog.video-props-dialog-shell .el-input__inner,
.el-dialog.video-props-dialog-shell .el-select__placeholder,
.el-dialog.video-props-dialog-shell .el-select__selected-item,
.video-props-dialog-shell .el-input__inner,
.video-props-dialog-shell .el-select__placeholder,
.video-props-dialog-shell .el-select__selected-item {
  color: #0f172a;
}

html.dark .el-dialog.video-props-dialog-shell .el-input__inner,
html.dark .el-dialog.video-props-dialog-shell .el-select__placeholder,
html.dark .el-dialog.video-props-dialog-shell .el-select__selected-item,
html.dark .video-props-dialog-shell .el-input__inner,
html.dark .video-props-dialog-shell .el-select__placeholder,
html.dark .video-props-dialog-shell .el-select__selected-item {
  color: #e2e8f0;
}

.el-dialog.video-props-dialog-shell .el-input__inner::placeholder,
.video-props-dialog-shell .el-input__inner::placeholder {
  color: rgba(100, 116, 139, 0.72);
}

html.dark .el-dialog.video-props-dialog-shell .el-input__inner::placeholder,
html.dark .video-props-dialog-shell .el-input__inner::placeholder {
  color: rgba(148, 163, 184, 0.72);
}

.el-dialog.video-props-dialog-shell .el-select__caret,
.el-dialog.video-props-dialog-shell .el-input__clear,
.video-props-dialog-shell .el-select__caret,
.video-props-dialog-shell .el-input__clear {
  color: rgba(100, 116, 139, 0.78);
}

html.dark .el-dialog.video-props-dialog-shell .el-select__caret,
html.dark .el-dialog.video-props-dialog-shell .el-input__clear,
html.dark .video-props-dialog-shell .el-select__caret,
html.dark .video-props-dialog-shell .el-input__clear {
  color: rgba(148, 163, 184, 0.78);
}

.video-props-select-popper.el-popper,
.video-props-select-popper.el-select__popper {
  border: 1px solid rgba(203, 213, 225, 0.95);
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98)) !important;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.14);
}

html.dark .video-props-select-popper.el-popper,
html.dark .video-props-select-popper.el-select__popper {
  border: 1px solid rgba(125, 211, 252, 0.14);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.98), rgba(15, 23, 42, 0.98)) !important;
  box-shadow: 0 18px 45px rgba(2, 6, 23, 0.42);
}

.video-props-select-popper.el-popper .el-popper__arrow::before,
.video-props-select-popper.el-select__popper .el-popper__arrow::before {
  border: 1px solid rgba(203, 213, 225, 0.95);
  background: rgba(255, 255, 255, 0.98) !important;
}

html.dark .video-props-select-popper.el-popper .el-popper__arrow::before,
html.dark .video-props-select-popper.el-select__popper .el-popper__arrow::before {
  border: 1px solid rgba(125, 211, 252, 0.14);
  background: rgba(17, 24, 39, 0.98) !important;
}

.video-props-select-popper .el-select-dropdown,
.video-props-select-popper .el-scrollbar,
.video-props-select-popper .el-scrollbar__view,
.video-props-select-popper .el-select-dropdown__wrap {
  background: transparent !important;
}

.video-props-select-popper .el-select-dropdown__list {
  padding: 8px;
  background: transparent !important;
}

.video-props-select-popper .el-select-dropdown__item {
  border-radius: 10px;
  color: #334155 !important;
}

html.dark .video-props-select-popper .el-select-dropdown__item {
  color: #dbeafe !important;
}

.video-props-select-popper .el-select-dropdown__item.hover,
.video-props-select-popper .el-select-dropdown__item:hover,
.video-props-select-popper .el-select-dropdown__item.is-hovering {
  background: rgba(34, 211, 238, 0.1) !important;
}

html.dark .video-props-select-popper .el-select-dropdown__item.hover,
html.dark .video-props-select-popper .el-select-dropdown__item:hover,
html.dark .video-props-select-popper .el-select-dropdown__item.is-hovering {
  background: rgba(34, 211, 238, 0.12) !important;
}

.video-props-select-popper .el-select-dropdown__item.selected {
  color: #0891b2 !important;
  font-weight: 600;
}

html.dark .video-props-select-popper .el-select-dropdown__item.selected {
  color: #a5f3fc !important;
}
</style>
