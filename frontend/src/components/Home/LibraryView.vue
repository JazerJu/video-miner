<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderOpen, Tag, FileText, Filter, SortAsc, ChevronDown, X, Check, Search } from 'lucide-vue-next'
import { ElMessage } from '@/composables/useNotification'
import type { Video } from '@/types/media'
import VideoCard from '@/components/Home/VideoCard.vue'
import BatchToolbar from '@/components/Home/BatchToolbar.vue'
import { BACKEND } from '@/composables/ConfigAPI'
import { getCSRFToken } from '@/composables/GetCSRFToken'
import { loadTags } from '@/composables/TagsAPI'

const { t } = useI18n()

const props = defineProps<{
  videos: Video[]
  batchMode: boolean
  selectedIds: number[]
}>()

const emit = defineEmits<{
  (e: 'update:selectedIds', ids: number[]): void
  (e: 'generateSubtitle', video: Video): void
  (e: 'delete', video: Video): void
  (e: 'editThumbnail', video: Video): void
  (e: 'renameVideo', ...args: [Video, string]): void
  (e: 'show-move-dialog'): void
  (e: 'generate-subtitles'): void
  (e: 'delete-videos'): void
  (e: 'videos-updated'): void
  (e: 'deselect-all'): void
}>()

/* ─── 筛选状态 ─── */
const showFilterPanel = ref<false | 'folders' | 'tags' | 'types'>(false)
const filterMode = ref<'include' | 'exclude'>('include')
const selectedFolders = ref<string[]>([])
const selectedTags = ref<string[]>([])
const selectedTypes = ref<string[]>([])

/* ─── 排序状态 ─── */
const sortBy = ref<'lastModified' | 'createdTime' | 'fileSize' | 'duration' | 'natural'>('lastModified')
const sortOrder = ref<'desc' | 'asc'>('desc')

/* ─── 分页状态 ─── */
const currentPage = ref(1)
const itemsPerPage = ref(20)

/* ─── 确认对话框状态 ─── */
const confirmDialog = ref<{
  visible: boolean
  type: 'folder' | 'tag'
  targetName: string
  targetId: number | null
}>({
  visible: false,
  type: 'folder',
  targetName: '',
  targetId: null,
})

/* ─── 选中视频的信息 ─── */
const selectedVideos = computed(() =>
  props.videos.filter(v => props.selectedIds.includes(v.id))
)

const selectedVideosFolders = computed(() => {
  const folders = new Set<string>()
  selectedVideos.value.forEach(v => {
    folders.add(v.categoryName || t('uncategorized'))
  })
  return Array.from(folders)
})

const selectedVideosTags = computed(() => {
  const tags = new Set<string>()
  selectedVideos.value.forEach(v => {
    if (v.tags && Array.isArray(v.tags)) {
      v.tags.forEach(tag => tags.add(tag))
    }
  })
  return Array.from(tags).sort()
})

const commonSelectedTags = computed(() => {
  if (selectedVideos.value.length === 0) return []
  const [firstVideo, ...restVideos] = selectedVideos.value
  const baseTags = new Set(firstVideo.tags || [])
  return Array.from(baseTags)
    .filter(tag => restVideos.every(video => (video.tags || []).includes(tag)))
    .sort()
})

/* ─── 可用选项 ─── */
const availableFolders = computed(() => {
  const folders = new Set<string>()
  props.videos.forEach(v => {
    folders.add(v.categoryName || t('uncategorized'))
  })
  return Array.from(folders).sort()
})

const allTagNames = ref<string[]>([])

async function fetchAllTags() {
  const tags = await loadTags()
  allTagNames.value = tags.map(t => t.name).sort()
}
fetchAllTags()

const availableTags = computed(() => allTagNames.value)

const fileTypes = computed(() => [
  { value: 'video', label: t('fileTypeVideo'), extensions: ['mp4', 'webm', 'mkv', 'avi', 'mov'] },
  { value: 'audio', label: t('fileTypeAudio'), extensions: ['mp3', 'm4a', 'wav', 'aac', 'flac'] },
])

const sortOptions = computed(() => [
  { value: 'lastModified', label: t('sortLastModified') },
  { value: 'createdTime', label: t('sortCreatedTime') },
  { value: 'fileSize', label: t('sortFileSize') },
  { value: 'duration', label: t('sortDuration') },
  { value: 'natural', label: t('sortNatural') },
])

const searchModeOptions = computed(() => [
  { value: 'title', label: t('searchModeTitle') },
  { value: 'title_content', label: t('searchModeTitleContent') },
  { value: 'subtitle', label: t('searchModeSubtitle') },
])

const searchMode = ref<'title' | 'title_content' | 'subtitle'>('title_content')
const showSearchModeDropdown = ref(false)
const searchQuery = ref('')

function closeSearchModeDropdown(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.search-mode-dropdown')) {
    showSearchModeDropdown.value = false
  }
}
onMounted(() => document.addEventListener('click', closeSearchModeDropdown))
onUnmounted(() => document.removeEventListener('click', closeSearchModeDropdown))
const activeSearchQuery = ref('')
const activeSearchMode = ref<'title' | 'title_content' | 'subtitle'>('title_content')
const searchMatchedIds = ref<number[] | null>(null)
const searchTotalMatches = ref(0)
const searchIsTruncated = ref(false)
const isSearching = ref(false)
const searchInputRef = ref<HTMLInputElement | null>(null)
let searchAbortController: AbortController | null = null

/* ─── 过滤 / 排序 / 分页 ─── */
const filteredVideos = computed(() => {
  let result = [...props.videos]

  if (activeSearchQuery.value && searchMatchedIds.value) {
    const matchedIdSet = new Set(searchMatchedIds.value)
    result = result.filter(v => matchedIdSet.has(v.id))
  }

  if (selectedFolders.value.length > 0) {
    result = result.filter(v => {
      const folderName = v.categoryName || t('uncategorized')
      const match = selectedFolders.value.includes(folderName)
      return filterMode.value === 'include' ? match : !match
    })
  }

  if (selectedTags.value.length > 0) {
    result = result.filter(v => {
      const videoTags = v.tags || []
      const match = selectedTags.value.some(tag => videoTags.includes(tag))
      return filterMode.value === 'include' ? match : !match
    })
  }

  if (selectedTypes.value.length > 0) {
    result = result.filter(v => {
      const ext = v.url?.split('.').pop()?.toLowerCase() || ''
      const isVideo = fileTypes.value[0].extensions.includes(ext)
      const isAudio = fileTypes.value[1].extensions.includes(ext)
      let match = false
      if (selectedTypes.value.includes('video') && isVideo) match = true
      if (selectedTypes.value.includes('audio') && isAudio) match = true
      return filterMode.value === 'include' ? match : !match
    })
  }

  return result
})

const sortedVideos = computed(() => {
  const result = [...filteredVideos.value]

  result.sort((a, b) => {
    let comparison = 0

    switch (sortBy.value) {
      case 'lastModified':
        comparison =
          new Date(b.last_accessed_at || b.last_modified || 0).getTime() -
          new Date(a.last_accessed_at || a.last_modified || 0).getTime()
        break
      case 'createdTime':
        comparison =
          new Date(b.added_at || b.file_created_time || 0).getTime() -
          new Date(a.added_at || a.file_created_time || 0).getTime()
        break
      case 'duration': {
        const durationA = a.video_length_seconds || parseDuration(a.length)
        const durationB = b.video_length_seconds || parseDuration(b.length)
        comparison = durationB - durationA
        break
      }
      case 'fileSize':
        comparison = (b.file_size || 0) - (a.file_size || 0)
        break
      case 'natural':
        comparison = a.name.localeCompare(b.name, undefined, { numeric: true })
        break
    }

    return sortOrder.value === 'asc' ? -comparison : comparison
  })

  return result
})

function parseDuration(duration: string | null | undefined): number {
  if (!duration) return 0
  const parts = duration.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return 0
}

const paginatedVideos = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value
  return sortedVideos.value.slice(start, start + itemsPerPage.value)
})

const totalPages = computed(() =>
  Math.ceil(sortedVideos.value.length / itemsPerPage.value)
)

/* ─── 交互方法 ─── */
function toggleSelection(id: number) {
  const newIds = props.selectedIds.includes(id)
    ? props.selectedIds.filter(i => i !== id)
    : [...props.selectedIds, id]
  emit('update:selectedIds', newIds)
}

function toggleFolder(folder: string) {
  const idx = selectedFolders.value.indexOf(folder)
  if (idx > -1) selectedFolders.value.splice(idx, 1)
  else selectedFolders.value.push(folder)
}

function toggleTag(tag: string) {
  const idx = selectedTags.value.indexOf(tag)
  if (idx > -1) selectedTags.value.splice(idx, 1)
  else selectedTags.value.push(tag)
}

function toggleType(type: string) {
  const idx = selectedTypes.value.indexOf(type)
  if (idx > -1) selectedTypes.value.splice(idx, 1)
  else selectedTypes.value.push(type)
}

function clearFilters() {
  selectedFolders.value = []
  selectedTags.value = []
  selectedTypes.value = []
}

async function performSearch() {
  const query = searchQuery.value.trim()

  if (!query) {
    activeSearchQuery.value = ''
    searchMatchedIds.value = null
    searchTotalMatches.value = 0
    searchIsTruncated.value = false
    return
  }

  // Cancel previous in-flight search
  if (searchAbortController) {
    searchAbortController.abort()
  }
  searchAbortController = new AbortController()

  isSearching.value = true

  try {
    const csrf = await getCSRFToken()
    const res = await fetch(`${BACKEND}/api/videos/search/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      body: JSON.stringify({
        query,
        mode: searchMode.value,
      }),
      signal: searchAbortController.signal,
    })

    if (!res.ok) throw new Error(t('searchFailed'))

    const data = await res.json()
    activeSearchQuery.value = query
    activeSearchMode.value = searchMode.value
    searchMatchedIds.value = Array.isArray(data.results) ? data.results.map((item: { id: number }) => item.id) : []
    searchTotalMatches.value = data.total_matches || 0
    searchIsTruncated.value = Boolean(data.truncated)
    currentPage.value = 1
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    console.error(error)
    ElMessage.error(t('searchFailedRetry'))
  } finally {
    isSearching.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  activeSearchQuery.value = ''
  activeSearchMode.value = searchMode.value
  searchMatchedIds.value = null
  searchTotalMatches.value = 0
  searchIsTruncated.value = false
}

function handleSearchKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    performSearch()
  } else if (event.key === 'Escape' && searchQuery.value) {
    clearSearch()
  }
}

function getFolderCount(folder: string): number {
  return props.videos.filter(v => (v.categoryName || t('uncategorized')) === folder).length
}

function getTagCount(tag: string): number {
  return props.videos.filter(v => v.tags?.includes(tag)).length
}

/* ─── 编辑模式: 点击文件夹/标签 → 弹出确认 ─── */

function getFolderCategoryId(folderName: string): number | null {
  const video = props.videos.find(v => (v.categoryName || t('uncategorized')) === folderName)
  if (!video || folderName === t('uncategorized')) return null
  return video.categoryId ?? null
}

function onAssignFolderClick(folder: string) {
  confirmDialog.value = {
    visible: true,
    type: 'folder',
    targetName: folder,
    targetId: getFolderCategoryId(folder),
  }
  showFilterPanel.value = false
}

function onAssignTagClick(tag: string) {
  confirmDialog.value = {
    visible: true,
    type: 'tag',
    targetName: tag,
    targetId: null,
  }
  showFilterPanel.value = false
}

async function confirmAssign() {
  const { type, targetName, targetId } = confirmDialog.value
  const ids = props.selectedIds

  try {
    const csrf = await getCSRFToken()

    if (type === 'folder') {
      const res = await fetch(`${BACKEND}/api/videos/batch_action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        credentials: 'include',
        body: JSON.stringify({
          action: 'move_category',
          videoIds: ids,
          categoryId: targetId,
        }),
      })
      const data = await res.json()
      if (data.success) {
        ElMessage.success(t('assignSuccess', { name: targetName, count: ids.length }))
      } else {
        ElMessage.error(data.error || t('assignFailed'))
      }
    } else {
      const shouldRemoveTag = commonSelectedTags.value.includes(targetName)
      const res = await fetch(`${BACKEND}/api/videos/batch_action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        credentials: 'include',
        body: JSON.stringify({
          action: shouldRemoveTag ? 'remove_tags' : 'add_tags',
          videoIds: ids,
          tagNames: [targetName],
        }),
      })
      const data = await res.json()
      if (data.success) {
        ElMessage.success(
          shouldRemoveTag
            ? t('tagRemoveSuccess', { count: ids.length, name: targetName })
            : t('tagAddSuccess', { count: ids.length, name: targetName }),
        )
      } else {
        ElMessage.error(data.error || t('tagUpdateFailed'))
      }
    }

    emit('videos-updated')
    fetchAllTags()
  } catch (e: any) {
    ElMessage.error(e.message || t('operationFailed'))
  } finally {
    confirmDialog.value.visible = false
  }
}

/* ─── Watchers ─── */
watch([selectedFolders, selectedTags, selectedTypes], () => {
  currentPage.value = 1
}, { deep: true })

watch([sortBy, sortOrder], () => {
  currentPage.value = 1
})

defineExpose({
  focusSearch: async () => {
    await nextTick()
    searchInputRef.value?.focus()
    searchInputRef.value?.select()
  },
})

const folderSearchQuery = ref('')
const tagSearchQuery = ref('')

const filteredFolderList = computed(() => {
  if (!folderSearchQuery.value) return availableFolders.value
  const q = folderSearchQuery.value.toLowerCase()
  return availableFolders.value.filter(f => f.toLowerCase().includes(q))
})

const filteredTagList = computed(() => {
  if (!tagSearchQuery.value) return availableTags.value
  const q = tagSearchQuery.value.toLowerCase()
  return availableTags.value.filter(t => t.toLowerCase().includes(q))
})

watch(showFilterPanel, (val) => {
  if (!val) {
    folderSearchQuery.value = ''
    tagSearchQuery.value = ''
  }
})
</script>

<template>
  <div class="library-view">
    <!-- 顶部工具栏 -->
    <div class="mb-6 space-y-4">
      <!-- 第一行：标题 + 排序 -->
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold text-slate-900 dark:text-white">
          {{ t('allMedia') }}
          <span v-if="batchMode" class="text-sm font-normal text-yellow-300 ml-2">
            {{ t('batchSelected', { count: selectedIds.length }) }}
          </span>
          <button
            v-if="batchMode"
            class="ml-2 inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600 transition hover:border-slate-300 hover:bg-slate-100 hover:text-slate-900 dark:border-white/12 dark:bg-white/[0.04] dark:text-slate-300 dark:hover:border-white/20 dark:hover:bg-white/[0.08] dark:hover:text-white"
            @click="emit('deselect-all')"
          >
            <X class="h-3 w-3" />
            {{ t('cancelSelection') }}
          </button>
        </h2>

        <!-- 排序控制 -->
        <div class="flex items-center space-x-2">
          <span class="text-sm text-slate-500 dark:text-white/60">{{ t('sortBy') }}</span>
          <div class="relative">
            <select
              v-model="sortBy"
              class="appearance-none bg-slate-100 text-slate-900 text-sm px-3 py-1.5 pr-8 rounded-lg border border-slate-200 focus:outline-none focus:border-blue-500 cursor-pointer dark:bg-gray-700/50 dark:text-white dark:border-white/10"
            >
              <option v-for="opt in sortOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <ChevronDown class="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none dark:text-white/60" />
          </div>
          <button
            @click="sortOrder = sortOrder === 'asc' ? 'desc' : 'asc'"
            class="p-1.5 rounded-lg bg-slate-100 text-slate-800 hover:bg-slate-200 transition-colors dark:bg-gray-700/50 dark:text-white/80 dark:hover:bg-gray-600/50"
            :title="sortOrder === 'asc' ? t('sortOrderAsc') : t('sortOrderDesc')"
          >
            <SortAsc class="w-4 h-4" :class="{ 'rotate-180': sortOrder === 'desc' }" />
          </button>
        </div>
      </div>

      <!-- 第二行：筛选 / 编辑 工具栏 -->
      <div class="flex items-center flex-wrap gap-2">
        <!-- ════════ 筛选模式 (无选中) ════════ -->
        <template v-if="!batchMode">
          <div class="flex min-w-[460px] max-w-[720px] flex-1 items-center overflow-visible rounded-xl bg-white shadow-[0_10px_24px_rgba(2,6,23,0.18)] dark:bg-slate-900/55">
            <div class="relative shrink-0 bg-slate-50 dark:bg-slate-800/75 search-mode-dropdown">
              <button
                @click="showSearchModeDropdown = !showSearchModeDropdown"
                class="flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-colors cursor-pointer"
              >
                {{ searchModeOptions.find(o => o.value === searchMode)?.label }}
                <ChevronDown class="h-4 w-4 text-slate-500 dark:text-white/45 transition-transform" :class="{ 'rotate-180': showSearchModeDropdown }" />
              </button>
              <div
                v-if="showSearchModeDropdown"
                class="absolute left-0 top-full mt-1 z-50 min-w-[120px] rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-600 dark:bg-slate-800 overflow-hidden"
              >
                <button
                  v-for="opt in searchModeOptions"
                  :key="opt.value"
                  @click="searchMode = opt.value as typeof searchMode; showSearchModeDropdown = false"
                  class="w-full px-3 py-2 text-left text-sm transition-colors cursor-pointer"
                  :class="searchMode === opt.value
                    ? 'bg-teal-50 text-teal-700 font-medium dark:bg-teal-900/30 dark:text-teal-300'
                    : 'text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-700/50'"
                >
                  {{ opt.label }}
                </button>
              </div>
            </div>

            <div class="relative min-w-0 flex-1">
              <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-white/35" />
              <input
                ref="searchInputRef"
                v-model="searchQuery"
                :placeholder="t('searchPlaceholder')"
                class="w-full border-0 bg-transparent py-2.5 pl-9 pr-10 text-sm text-slate-900 placeholder-slate-400 focus:outline-none dark:text-white dark:placeholder-white/35"
                @keydown="handleSearchKeydown"
              />
              <button
                v-if="searchQuery || activeSearchQuery"
                class="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:text-white/45 dark:hover:bg-white/8 dark:hover:text-white/80"
                @click="clearSearch"
              >
                <X class="h-4 w-4" />
              </button>
            </div>
          </div>

          <!-- 包含/排除切换 -->
          <div class="flex bg-slate-50 rounded-lg p-0.5 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
            <button
              @click="filterMode = 'include'"
              :class="[
                'px-3 py-1 text-xs rounded-md transition-all duration-200',
                filterMode === 'include' ? 'bg-green-600 text-white' : 'text-slate-500 hover:text-slate-900 dark:text-gray-400 dark:hover:text-white'
              ]"
            >
              {{ t('filterInclude') }}
            </button>
            <button
              @click="filterMode = 'exclude'"
              :class="[
                'px-3 py-1 text-xs rounded-md transition-all duration-200',
                filterMode === 'exclude' ? 'bg-red-600 text-white' : 'text-slate-500 hover:text-slate-900 dark:text-gray-400 dark:hover:text-white'
              ]"
            >
              {{ t('filterExclude') }}
            </button>
          </div>

          <!-- 文件夹筛选 -->
          <div class="relative">
            <button
              @click="showFilterPanel = showFilterPanel === 'folders' ? false : 'folders'"
              :class="[
                'flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-all border',
                selectedFolders.length > 0
                  ? 'bg-blue-50 border-blue-300 text-blue-700 dark:bg-blue-600/30 dark:border-blue-500/50 dark:text-blue-200'
                  : 'bg-slate-100 border-slate-200 text-slate-800 hover:bg-slate-200 dark:bg-gray-700/50 dark:border-white/10 dark:text-white/80 dark:hover:bg-gray-600/50'
              ]"
            >
              <FolderOpen class="w-4 h-4" />
              <span>{{ t('filterFolders') }}</span>
              <span v-if="selectedFolders.length > 0" class="bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full text-xs dark:bg-blue-500/50 dark:text-blue-200">
                {{ selectedFolders.length }}
              </span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'folders'" class="absolute top-full left-0 mt-2 w-64 bg-white rounded-lg border border-slate-200 shadow-xl z-50 max-h-80 overflow-y-auto dark:bg-gray-800 dark:border-white/10">
              <div class="p-3 border-b border-slate-200 flex items-center justify-between dark:border-white/10">
                <span class="text-sm font-medium text-slate-900 dark:text-white">{{ t('selectFolders') }}</span>
                <button @click="selectedFolders = []" class="text-xs text-red-400 hover:text-red-300">{{ t('clear') }}</button>
              </div>
              <div class="p-2 border-b border-slate-200 dark:border-white/10">
                <input
                  v-model="tagSearchQuery"
                  :placeholder="t('filterTagPlaceholder2')"
                  class="w-full bg-slate-100 text-slate-900 text-sm px-3 py-1.5 rounded-lg border border-slate-200 focus:outline-none focus:border-blue-500 placeholder-slate-400 dark:bg-gray-700/50 dark:text-white dark:border-white/10 dark:placeholder-white/40"
                />
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="folder in filteredFolderList"
                  :key="folder"
                  @click="toggleFolder(folder)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    selectedFolders.includes(folder) ? 'bg-blue-50 text-blue-700 dark:bg-blue-600/30 dark:text-blue-200' : 'hover:bg-slate-100 text-slate-800 dark:hover:bg-white/5 dark:text-white/80'
                  ]"
                >
                  <span class="text-sm">{{ folder }}</span>
                  <span class="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full dark:text-white/50 dark:bg-white/10">{{ getFolderCount(folder) }}</span>
                </div>
                <div v-if="availableFolders.length === 0" class="text-center py-4 text-slate-400 text-sm dark:text-white/40">
                  {{ t('noFolders') }}
                </div>
              </div>
            </div>
          </div>

          <!-- 标签筛选 -->
          <div class="relative">
            <button
              @click="showFilterPanel = showFilterPanel === 'tags' ? false : 'tags'"
              :class="[
                'flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-all border',
                selectedTags.length > 0
                  ? 'bg-green-50 border-green-300 text-green-700 dark:bg-green-600/30 dark:border-green-500/50 dark:text-green-200'
                  : 'bg-slate-100 border-slate-200 text-slate-800 hover:bg-slate-200 dark:bg-gray-700/50 dark:border-white/10 dark:text-white/80 dark:hover:bg-gray-600/50'
              ]"
            >
              <Tag class="w-4 h-4" />
              <span>{{ t('filterTags') }}</span>
              <span v-if="selectedTags.length > 0" class="bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full text-xs dark:bg-green-500/50 dark:text-green-200">
                {{ selectedTags.length }}
              </span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'tags'" class="absolute top-full left-0 mt-2 w-64 bg-white rounded-lg border border-slate-200 shadow-xl z-50 max-h-80 overflow-y-auto dark:bg-gray-800 dark:border-white/10">
              <div class="p-3 border-b border-slate-200 flex items-center justify-between dark:border-white/10">
                <span class="text-sm font-medium text-slate-900 dark:text-white">{{ t('selectTags') }}</span>
                <button @click="selectedTags = []" class="text-xs text-red-400 hover:text-red-300">{{ t('clear') }}</button>
              </div>
              <div class="p-2 border-b border-slate-200 dark:border-white/10">
                <input
                  v-model="tagSearchQuery"
                  placeholder="筛选标签..."
                  class="w-full bg-slate-100 text-slate-900 text-sm px-3 py-1.5 rounded-lg border border-slate-200 focus:outline-none focus:border-blue-500 placeholder-slate-400 dark:bg-gray-700/50 dark:text-white dark:border-white/10 dark:placeholder-white/40"
                />
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="tag in filteredTagList"
                  :key="tag"
                  @click="toggleTag(tag)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    selectedTags.includes(tag) ? 'bg-green-50 text-green-700 dark:bg-green-600/30 dark:text-green-200' : 'hover:bg-slate-100 text-slate-800 dark:hover:bg-white/5 dark:text-white/80'
                  ]"
                >
                  <span class="text-sm">{{ tag }}</span>
                  <span class="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full dark:text-white/50 dark:bg-white/10">{{ getTagCount(tag) }}</span>
                </div>
                <div v-if="availableTags.length === 0" class="text-center py-4 text-slate-400 text-sm dark:text-white/40">
                  {{ t('noTags') }}
                </div>
              </div>
            </div>
          </div>

          <!-- 类型筛选 -->
          <div class="relative">
            <button
              @click="showFilterPanel = showFilterPanel === 'types' ? false : 'types'"
              :class="[
                'flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-all border',
                selectedTypes.length > 0
                  ? 'bg-purple-50 border-purple-300 text-purple-700 dark:bg-purple-600/30 dark:border-purple-500/50 dark:text-purple-200'
                  : 'bg-slate-100 border-slate-200 text-slate-800 hover:bg-slate-200 dark:bg-gray-700/50 dark:border-white/10 dark:text-white/80 dark:hover:bg-gray-600/50'
              ]"
            >
              <FileText class="w-4 h-4" />
              <span>{{ t('filterTypes') }}</span>
              <span v-if="selectedTypes.length > 0" class="bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded-full text-xs dark:bg-purple-500/50 dark:text-purple-200">
                {{ selectedTypes.length }}
              </span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'types'" class="absolute top-full left-0 mt-2 w-48 bg-white rounded-lg border border-slate-200 shadow-xl z-50 dark:bg-gray-800 dark:border-white/10">
              <div class="p-3 border-b border-slate-200 dark:border-white/10">
                <span class="text-sm font-medium text-slate-900 dark:text-white">{{ t('fileType') }}</span>
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="type in fileTypes"
                  :key="type.value"
                  @click="toggleType(type.value)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    selectedTypes.includes(type.value) ? 'bg-purple-50 text-purple-700 dark:bg-purple-600/30 dark:text-purple-200' : 'hover:bg-slate-100 text-slate-800 dark:hover:bg-white/5 dark:text-white/80'
                  ]"
                >
                  <span class="text-sm">{{ type.label }}</span>
                  <span class="text-xs text-slate-400 dark:text-white/50">{{ type.extensions.join(', ') }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 清除筛选 -->
          <button
            v-if="selectedFolders.length > 0 || selectedTags.length > 0 || selectedTypes.length > 0"
            @click="clearFilters"
            class="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm bg-red-50 border border-red-200 text-red-600 hover:bg-red-100 transition-colors dark:bg-red-600/20 dark:border-red-500/30 dark:text-red-300 dark:hover:bg-red-600/30"
          >
            <X class="w-4 h-4" />
            <span>{{ t('clearFilters') }}</span>
          </button>
        </template>

        <!-- ════════ 编辑模式 (有选中) ════════ -->
        <template v-else>
          <!-- 存储路径 (Folder) 分配下拉 -->
          <div class="relative">
            <button
              @click="showFilterPanel = showFilterPanel === 'folders' ? false : 'folders'"
              class="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-all border bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100 dark:bg-amber-600/30 dark:border-amber-500/50 dark:text-amber-200 dark:hover:bg-amber-600/40"
            >
              <FolderOpen class="w-4 h-4" />
              <span>{{ t('savePath') }}</span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'folders'" class="absolute top-full left-0 mt-2 w-72 bg-white rounded-lg border border-slate-200 shadow-xl z-50 max-h-96 overflow-y-auto dark:bg-gray-800 dark:border-white/10">
              <!-- 当前选中视频的 Folder -->
              <div class="p-3 border-b border-slate-200 dark:border-white/10">
                <span class="text-xs text-slate-400 mb-1 block dark:text-white/50">{{ t('selectedVideosFolders') }}</span>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="f in selectedVideosFolders"
                    :key="f"
                    class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-600/30 dark:text-amber-200 dark:border-amber-500/30"
                  >
                    <Check class="w-3 h-3 mr-1" />
                    {{ f }}
                  </span>
                </div>
              </div>
              <div class="p-2 border-b border-slate-200 dark:border-white/10">
                <input
                  v-model="folderSearchQuery"
                  :placeholder="t('filterFolderPlaceholder2')"
                  class="w-full bg-slate-100 text-slate-900 text-sm px-3 py-1.5 rounded-lg border border-slate-200 focus:outline-none focus:border-blue-500 placeholder-slate-400 dark:bg-gray-700/50 dark:text-white dark:border-white/10 dark:placeholder-white/40"
                />
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="folder in filteredFolderList"
                  :key="folder"
                  @click="onAssignFolderClick(folder)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    selectedVideosFolders.includes(folder) ? 'bg-amber-50 text-amber-700 dark:bg-amber-600/20 dark:text-amber-200' : 'hover:bg-slate-100 text-slate-800 dark:hover:bg-white/5 dark:text-white/80'
                  ]"
                >
                  <span class="text-sm">{{ folder }}</span>
                  <span class="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full dark:text-white/50 dark:bg-white/10">{{ getFolderCount(folder) }}</span>
                </div>
                <div v-if="availableFolders.length === 0" class="text-center py-4 text-slate-400 text-sm dark:text-white/40">
                  {{ t('noStoragePath') }}
                </div>
              </div>
            </div>
          </div>

          <!-- 标签分配下拉 -->
          <div class="relative">
            <button
              @click="showFilterPanel = showFilterPanel === 'tags' ? false : 'tags'"
              class="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-all border bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-600/30 dark:border-emerald-500/50 dark:text-emerald-200 dark:hover:bg-emerald-600/40"
            >
              <Tag class="w-4 h-4" />
              <span>{{ t('filterTags') }}</span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'tags'" class="absolute top-full left-0 mt-2 w-72 bg-white rounded-lg border border-slate-200 shadow-xl z-50 max-h-96 overflow-y-auto dark:bg-gray-800 dark:border-white/10">
              <!-- 当前选中视频的标签 -->
              <div class="p-3 border-b border-slate-200 dark:border-white/10">
                <span class="text-xs text-slate-400 mb-1 block dark:text-white/50">{{ t('selectedVideosTags') }}</span>
                <div v-if="selectedVideosTags.length > 0" class="flex flex-wrap gap-1">
                  <span
                    v-for="tg in selectedVideosTags"
                    :key="tg"
                    :class="[
                      'inline-flex items-center px-2 py-0.5 rounded text-xs border',
                      commonSelectedTags.includes(tg)
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-600/30 dark:text-emerald-200 dark:border-emerald-500/30'
                        : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-200 dark:border-amber-400/25',
                    ]"
                  >
                    <Check v-if="commonSelectedTags.includes(tg)" class="w-3 h-3 mr-1" />
                    {{ tg }}
                  </span>
                </div>
                <span v-else class="text-xs text-slate-300 dark:text-white/30">{{ t('noTagsSelected') }}</span>
              </div>
              <div class="p-2 border-b border-slate-200 dark:border-white/10">
                <input
                  v-model="tagSearchQuery"
                  placeholder="筛选标签..."
                  class="w-full bg-slate-100 text-slate-900 text-sm px-3 py-1.5 rounded-lg border border-slate-200 focus:outline-none focus:border-blue-500 placeholder-slate-400 dark:bg-gray-700/50 dark:text-white dark:border-white/10 dark:placeholder-white/40"
                />
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="tag in filteredTagList"
                  :key="tag"
                  @click="onAssignTagClick(tag)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    commonSelectedTags.includes(tag)
                      ? 'bg-rose-50 text-rose-700 dark:bg-rose-600/20 dark:text-rose-200'
                      : selectedVideosTags.includes(tag)
                        ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200'
                        : 'hover:bg-slate-100 text-slate-800 dark:hover:bg-white/5 dark:text-white/80'
                  ]"
                >
                  <div class="flex items-center gap-2">
                    <span class="text-sm">{{ tag }}</span>
                    <span
                      v-if="commonSelectedTags.includes(tag)"
                      class="rounded-full border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] font-medium text-rose-700 dark:border-rose-400/30 dark:bg-rose-500/15 dark:text-rose-200"
                    >
                      {{ t('clickToRemove') }}
                    </span>
                    <span
                      v-else-if="selectedVideosTags.includes(tag)"
                      class="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-400/25 dark:bg-amber-500/10 dark:text-amber-200"
                    >
                      {{ t('partiallyOwned') }}
                    </span>
                  </div>
                  <span class="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full dark:text-white/50 dark:bg-white/10">{{ getTagCount(tag) }}</span>
                </div>
                <div v-if="availableTags.length === 0" class="text-center py-4 text-slate-400 text-sm dark:text-white/40">
                  {{ t('noTags') }}
                </div>
              </div>
            </div>
          </div>

          <!-- 批量操作按钮 -->
          <BatchToolbar
            :batch-mode="batchMode"
            :selected-ids="selectedIds"
            @show-move-dialog="emit('show-move-dialog')"
            @generate-subtitles="emit('generate-subtitles')"
            @delete-videos="emit('delete-videos')"
            @deselect-all="emit('deselect-all')"
          />
        </template>
      </div>

      <!-- 结果统计 -->
      <div class="flex flex-wrap items-center gap-3 text-sm text-slate-400 dark:text-white/50">
        <span>{{ t('resultCount', { total: filteredVideos.length, shown: paginatedVideos.length }) }}</span>
        <span v-if="isSearching" class="text-cyan-700 dark:text-cyan-200/80">{{ t('searching') }}</span>
        <span v-else-if="activeSearchQuery" class="rounded-full border border-cyan-300/40 bg-cyan-50 px-2.5 py-1 text-cyan-700 dark:border-cyan-400/20 dark:bg-cyan-500/10 dark:text-cyan-100">
          {{ searchModeOptions.find(item => item.value === activeSearchMode)?.label }}:
          "{{ activeSearchQuery }}"
          <span class="ml-1 text-cyan-600 dark:text-cyan-200/70">{{ t('searchResultMatch', { count: searchTotalMatches }) }}</span>
        </span>
        <span v-if="searchIsTruncated" class="text-amber-600 dark:text-amber-300/80">
          {{ t('searchTruncated') }}
        </span>
      </div>
    </div>

    <!-- 点击外部关闭下拉面板 -->
    <div v-if="showFilterPanel" class="fixed inset-0 z-40" @click="showFilterPanel = false"></div>

    <!-- 视频网格 -->
    <div v-if="paginatedVideos.length > 0" class="grid gap-5 grid-cols-[repeat(auto-fit,minmax(240px,300px))]">
      <VideoCard
        v-for="video in paginatedVideos"
        :key="video.id"
        :video="video"
        view="grid"
        :batch-mode="batchMode"
        :checked="selectedIds.includes(video.id)"
        @update:checked="() => toggleSelection(video.id)"
        @edit-thumbnail="() => $emit('editThumbnail', video)"
        @generate-subtitle="() => $emit('generateSubtitle', video)"
        @delete="() => $emit('delete', video)"
        @rename-video="(v: Video, name: string) => $emit('renameVideo', v, name)"
      />
    </div>

    <!-- 空状态 -->
    <div v-else-if="filteredVideos.length === 0 && props.videos.length > 0" class="flex items-center justify-center py-12">
      <div class="text-center">
        <Filter class="w-16 h-16 mx-auto mb-4 text-slate-300 dark:text-white/30" />
        <p class="text-slate-500 text-lg mb-2 dark:text-white/60">{{ t('noMatchFound') }}</p>
        <p class="text-slate-400 text-sm mb-4 dark:text-white/40">
          {{ activeSearchQuery ? t('noMatchTryOther') : t('adjustFilters') }}
        </p>
        <div class="flex items-center justify-center gap-3">
          <button @click="clearFilters" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors">
            {{ t('clearFilters') }}
          </button>
          <button
            v-if="activeSearchQuery"
            @click="clearSearch"
            class="px-4 py-2 rounded-lg border border-slate-300 bg-slate-50 text-slate-800 transition-colors hover:bg-slate-100 dark:border-white/15 dark:bg-white/5 dark:text-white/80 dark:hover:bg-white/10"
          >
            {{ t('clear') }}
          </button>
        </div>
      </div>
    </div>

    <div v-else class="flex items-center justify-center py-12">
      <div class="text-center">
        <p class="text-slate-500 text-lg mb-2 dark:text-white/60">{{ t('emptyNoVideos') }}</p>
        <p class="text-slate-400 text-sm dark:text-white/40">{{ t('emptyUploadPrompt') }}</p>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="flex justify-center mt-8">
      <div class="flex items-center space-x-2">
        <button
          @click="currentPage--"
          :disabled="currentPage === 1"
          :class="[
            'px-3 py-1.5 rounded-lg text-sm transition-colors',
            currentPage === 1
              ? 'bg-slate-100 text-slate-300 cursor-not-allowed dark:bg-gray-700/30 dark:text-white/30'
              : 'bg-slate-100 text-slate-900 hover:bg-slate-200 dark:bg-gray-700/50 dark:text-white dark:hover:bg-gray-600/50'
          ]"
        >
            {{ t('prevPage') }}
        </button>

        <div class="flex items-center space-x-1">
          <button
            v-for="page in totalPages"
            :key="page"
            @click="currentPage = page"
            :class="[
              'w-8 h-8 rounded-lg text-sm transition-colors',
              currentPage === page
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-gray-700/50 dark:text-white/70 dark:hover:bg-gray-600/50'
            ]"
          >
            {{ page }}
          </button>
        </div>

        <button
          @click="currentPage++"
          :disabled="currentPage === totalPages"
          :class="[
            'px-3 py-1.5 rounded-lg text-sm transition-colors',
            currentPage === totalPages
              ? 'bg-slate-100 text-slate-300 cursor-not-allowed dark:bg-gray-700/30 dark:text-white/30'
              : 'bg-slate-100 text-slate-900 hover:bg-slate-200 dark:bg-gray-700/50 dark:text-white dark:hover:bg-gray-600/50'
          ]"
        >
            {{ t('nextPage') }}
        </button>
      </div>
    </div>

    <!-- ════════ 确认对话框 ════════ -->
    <Teleport to="body">
      <div
        v-if="confirmDialog.visible"
        class="fixed inset-0 z-[9999] flex items-center justify-center"
      >
        <!-- 遮罩 -->
        <div class="absolute inset-0 bg-black/60" @click="confirmDialog.visible = false"></div>

        <!-- 对话框 -->
        <div class="relative bg-white rounded-xl border border-slate-200 shadow-2xl w-[420px] max-w-[90vw] dark:bg-[#1a1a2e] dark:border-white/10">
          <!-- 标题栏 -->
          <div class="flex items-center justify-between p-5 pb-3">
            <h3 class="text-lg font-bold text-slate-900 dark:text-white">
              {{ confirmDialog.type === 'folder' ? t('confirmFolderAssign') : t('confirmTagAssign') }}
            </h3>
            <button
              @click="confirmDialog.visible = false"
              class="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-900 hover:bg-slate-100 transition-colors dark:text-white/50 dark:hover:text-white dark:hover:bg-white/10"
            >
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- 内容 -->
          <div class="px-5 pb-5">
            <p class="text-green-600 text-sm leading-relaxed mb-6 dark:text-green-400">
              <template v-if="confirmDialog.type === 'folder'">
                {{ t('confirmFolderDesc', { name: confirmDialog.targetName, count: selectedIds.length }) }}
              </template>
              <template v-else>
                {{ t('confirmTagDesc', { name: confirmDialog.targetName, count: selectedIds.length }) }}
              </template>
            </p>

            <!-- 按钮区 -->
            <div class="flex justify-end gap-3">
              <button
                @click="confirmDialog.visible = false"
                class="px-5 py-2 rounded-lg text-sm text-slate-800 border border-slate-300 hover:bg-slate-100 transition-colors dark:text-white/80 dark:border-white/20 dark:hover:bg-white/10"
              >
                {{ t('cancelBtn') }}
              </button>
              <button
                @click="confirmAssign"
                class="px-5 py-2 rounded-lg text-sm text-black font-medium bg-amber-500 hover:bg-amber-400 transition-colors"
              >
                {{ t('confirmBtn') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.library-view {
  @apply w-full;
}

::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}
</style>
