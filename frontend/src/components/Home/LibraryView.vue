<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
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
    folders.add(v.categoryName || '未分类')
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
    folders.add(v.categoryName || '未分类')
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

const fileTypes = [
  { value: 'video', label: '视频', extensions: ['mp4', 'webm', 'mkv', 'avi', 'mov'] },
  { value: 'audio', label: '音频', extensions: ['mp3', 'm4a', 'wav', 'aac', 'flac'] },
]

const sortOptions = [
  { value: 'lastModified', label: '最后访问时间' },
  { value: 'createdTime', label: '创建时间' },
  { value: 'fileSize', label: '文件大小' },
  { value: 'duration', label: '视频时长' },
  { value: 'natural', label: '自然排序' },
]

const searchModeOptions = [
  { value: 'title', label: '标题' },
  { value: 'title_content', label: '标题&内容' },
  { value: 'subtitle', label: '纯字幕' },
]

const searchMode = ref<'title' | 'title_content' | 'subtitle'>('title_content')
const searchQuery = ref('')
const activeSearchQuery = ref('')
const activeSearchMode = ref<'title' | 'title_content' | 'subtitle'>('title_content')
const searchMatchedIds = ref<number[] | null>(null)
const searchTotalMatches = ref(0)
const searchIsTruncated = ref(false)
const isSearching = ref(false)
const searchInputRef = ref<HTMLInputElement | null>(null)

/* ─── 过滤 / 排序 / 分页 ─── */
const filteredVideos = computed(() => {
  let result = [...props.videos]

  if (activeSearchQuery.value && searchMatchedIds.value) {
    const matchedIdSet = new Set(searchMatchedIds.value)
    result = result.filter(v => matchedIdSet.has(v.id))
  }

  if (selectedFolders.value.length > 0) {
    result = result.filter(v => {
      const folderName = v.categoryName || '未分类'
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
      const isVideo = fileTypes[0].extensions.includes(ext)
      const isAudio = fileTypes[1].extensions.includes(ext)
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
    })

    if (!res.ok) throw new Error('搜索失败')

    const data = await res.json()
    activeSearchQuery.value = query
    activeSearchMode.value = searchMode.value
    searchMatchedIds.value = Array.isArray(data.results) ? data.results.map((item: { id: number }) => item.id) : []
    searchTotalMatches.value = data.total_matches || 0
    searchIsTruncated.value = Boolean(data.truncated)
    currentPage.value = 1
  } catch (error) {
    console.error(error)
    ElMessage.error('搜索失败，请稍后重试')
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
  return props.videos.filter(v => (v.categoryName || '未分类') === folder).length
}

function getTagCount(tag: string): number {
  return props.videos.filter(v => v.tags?.includes(tag)).length
}

/* ─── 编辑模式: 点击文件夹/标签 → 弹出确认 ─── */

function getFolderCategoryId(folderName: string): number | null {
  const video = props.videos.find(v => (v.categoryName || '未分类') === folderName)
  if (!video || folderName === '未分类') return null
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
        ElMessage.success(`已将存储路径"${targetName}"分配给 ${ids.length} 选定的文档。`)
      } else {
        ElMessage.error(data.error || '分配失败')
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
            ? `已从 ${ids.length} 个选定项目移除标签"${targetName}"。`
            : `已把标签"${targetName}"添加到 ${ids.length} 个选定项目。`,
        )
      } else {
        ElMessage.error(data.error || (shouldRemoveTag ? '移除标签失败' : '添加标签失败'))
      }
    }

    emit('videos-updated')
    fetchAllTags()
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
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
        <h2 class="text-xl font-bold text-white">
          {{ t('allMedia') }}
          <span v-if="batchMode" class="text-sm font-normal text-yellow-300 ml-2">
            — 已选 {{ selectedIds.length }} 项
          </span>
        </h2>

        <!-- 排序控制 -->
        <div class="flex items-center space-x-2">
          <span class="text-sm text-white/60">排序：</span>
          <div class="relative">
            <select
              v-model="sortBy"
              class="appearance-none bg-gray-700/50 text-white text-sm px-3 py-1.5 pr-8 rounded-lg border border-white/10 focus:outline-none focus:border-blue-500 cursor-pointer"
            >
              <option v-for="opt in sortOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <ChevronDown class="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-white/60 pointer-events-none" />
          </div>
          <button
            @click="sortOrder = sortOrder === 'asc' ? 'desc' : 'asc'"
            class="p-1.5 rounded-lg bg-gray-700/50 text-white/80 hover:bg-gray-600/50 transition-colors"
            :title="sortOrder === 'asc' ? '升序' : '降序'"
          >
            <SortAsc class="w-4 h-4" :class="{ 'rotate-180': sortOrder === 'desc' }" />
          </button>
        </div>
      </div>

      <!-- 第二行：筛选 / 编辑 工具栏 -->
      <div class="flex items-center flex-wrap gap-2">
        <!-- ════════ 筛选模式 (无选中) ════════ -->
        <template v-if="!batchMode">
          <div class="flex min-w-[460px] max-w-[720px] flex-1 items-center overflow-hidden rounded-xl bg-slate-900/55 shadow-[0_10px_24px_rgba(2,6,23,0.18)]">
            <div class="relative shrink-0 border-r border-white/8 bg-slate-800/75">
              <select
                v-model="searchMode"
                class="appearance-none bg-slate-800/95 px-3 py-2.5 pr-8 text-sm font-medium text-slate-100 focus:outline-none"
              >
                <option v-for="opt in searchModeOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <ChevronDown class="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-white/45" />
            </div>

            <div class="relative min-w-0 flex-1">
              <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
              <input
                ref="searchInputRef"
                v-model="searchQuery"
                placeholder="按 Enter 搜索标题、内容或字幕"
                class="w-full border-0 bg-transparent py-2.5 pl-9 pr-10 text-sm text-white placeholder-white/35 focus:outline-none"
                @keydown="handleSearchKeydown"
              />
              <button
                v-if="searchQuery || activeSearchQuery"
                class="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-white/45 transition hover:bg-white/8 hover:text-white/80"
                @click="clearSearch"
              >
                <X class="h-4 w-4" />
              </button>
            </div>
          </div>

          <!-- 包含/排除切换 -->
          <div class="flex bg-gray-800/50 rounded-lg p-0.5 border border-white/10">
            <button
              @click="filterMode = 'include'"
              :class="[
                'px-3 py-1 text-xs rounded-md transition-all duration-200',
                filterMode === 'include' ? 'bg-green-600 text-white' : 'text-gray-400 hover:text-white'
              ]"
            >
              包含
            </button>
            <button
              @click="filterMode = 'exclude'"
              :class="[
                'px-3 py-1 text-xs rounded-md transition-all duration-200',
                filterMode === 'exclude' ? 'bg-red-600 text-white' : 'text-gray-400 hover:text-white'
              ]"
            >
              排除
            </button>
          </div>

          <!-- 文件夹筛选 -->
          <div class="relative">
            <button
              @click="showFilterPanel = showFilterPanel === 'folders' ? false : 'folders'"
              :class="[
                'flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-all border',
                selectedFolders.length > 0
                  ? 'bg-blue-600/30 border-blue-500/50 text-blue-200'
                  : 'bg-gray-700/50 border-white/10 text-white/80 hover:bg-gray-600/50'
              ]"
            >
              <FolderOpen class="w-4 h-4" />
              <span>文件夹</span>
              <span v-if="selectedFolders.length > 0" class="bg-blue-500/50 px-1.5 py-0.5 rounded-full text-xs">
                {{ selectedFolders.length }}
              </span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'folders'" class="absolute top-full left-0 mt-2 w-64 bg-gray-800 rounded-lg border border-white/10 shadow-xl z-50 max-h-80 overflow-y-auto">
              <div class="p-3 border-b border-white/10 flex items-center justify-between">
                <span class="text-sm font-medium text-white">选择文件夹</span>
                <button @click="selectedFolders = []" class="text-xs text-red-400 hover:text-red-300">清除</button>
              </div>
              <div class="p-2 border-b border-white/10">
                <input
                  v-model="folderSearchQuery"
                  placeholder="筛选文件夹..."
                  class="w-full bg-gray-700/50 text-white text-sm px-3 py-1.5 rounded-lg border border-white/10 focus:outline-none focus:border-blue-500 placeholder-white/40"
                />
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="folder in filteredFolderList"
                  :key="folder"
                  @click="toggleFolder(folder)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    selectedFolders.includes(folder) ? 'bg-blue-600/30 text-blue-200' : 'hover:bg-white/5 text-white/80'
                  ]"
                >
                  <span class="text-sm">{{ folder }}</span>
                  <span class="text-xs text-white/50 bg-white/10 px-2 py-0.5 rounded-full">{{ getFolderCount(folder) }}</span>
                </div>
                <div v-if="availableFolders.length === 0" class="text-center py-4 text-white/40 text-sm">
                  暂无文件夹
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
                  ? 'bg-green-600/30 border-green-500/50 text-green-200'
                  : 'bg-gray-700/50 border-white/10 text-white/80 hover:bg-gray-600/50'
              ]"
            >
              <Tag class="w-4 h-4" />
              <span>标签</span>
              <span v-if="selectedTags.length > 0" class="bg-green-500/50 px-1.5 py-0.5 rounded-full text-xs">
                {{ selectedTags.length }}
              </span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'tags'" class="absolute top-full left-0 mt-2 w-64 bg-gray-800 rounded-lg border border-white/10 shadow-xl z-50 max-h-80 overflow-y-auto">
              <div class="p-3 border-b border-white/10 flex items-center justify-between">
                <span class="text-sm font-medium text-white">选择标签</span>
                <button @click="selectedTags = []" class="text-xs text-red-400 hover:text-red-300">清除</button>
              </div>
              <div class="p-2 border-b border-white/10">
                <input
                  v-model="tagSearchQuery"
                  placeholder="筛选标签..."
                  class="w-full bg-gray-700/50 text-white text-sm px-3 py-1.5 rounded-lg border border-white/10 focus:outline-none focus:border-blue-500 placeholder-white/40"
                />
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="tag in filteredTagList"
                  :key="tag"
                  @click="toggleTag(tag)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    selectedTags.includes(tag) ? 'bg-green-600/30 text-green-200' : 'hover:bg-white/5 text-white/80'
                  ]"
                >
                  <span class="text-sm">{{ tag }}</span>
                  <span class="text-xs text-white/50 bg-white/10 px-2 py-0.5 rounded-full">{{ getTagCount(tag) }}</span>
                </div>
                <div v-if="availableTags.length === 0" class="text-center py-4 text-white/40 text-sm">
                  暂无标签
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
                  ? 'bg-purple-600/30 border-purple-500/50 text-purple-200'
                  : 'bg-gray-700/50 border-white/10 text-white/80 hover:bg-gray-600/50'
              ]"
            >
              <FileText class="w-4 h-4" />
              <span>类型</span>
              <span v-if="selectedTypes.length > 0" class="bg-purple-500/50 px-1.5 py-0.5 rounded-full text-xs">
                {{ selectedTypes.length }}
              </span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'types'" class="absolute top-full left-0 mt-2 w-48 bg-gray-800 rounded-lg border border-white/10 shadow-xl z-50">
              <div class="p-3 border-b border-white/10">
                <span class="text-sm font-medium text-white">文件类型</span>
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="type in fileTypes"
                  :key="type.value"
                  @click="toggleType(type.value)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    selectedTypes.includes(type.value) ? 'bg-purple-600/30 text-purple-200' : 'hover:bg-white/5 text-white/80'
                  ]"
                >
                  <span class="text-sm">{{ type.label }}</span>
                  <span class="text-xs text-white/50">{{ type.extensions.join(', ') }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 清除筛选 -->
          <button
            v-if="selectedFolders.length > 0 || selectedTags.length > 0 || selectedTypes.length > 0"
            @click="clearFilters"
            class="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm bg-red-600/20 border border-red-500/30 text-red-300 hover:bg-red-600/30 transition-colors"
          >
            <X class="w-4 h-4" />
            <span>清除筛选</span>
          </button>
        </template>

        <!-- ════════ 编辑模式 (有选中) ════════ -->
        <template v-else>
          <!-- 存储路径 (Folder) 分配下拉 -->
          <div class="relative">
            <button
              @click="showFilterPanel = showFilterPanel === 'folders' ? false : 'folders'"
              class="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-all border bg-amber-600/30 border-amber-500/50 text-amber-200 hover:bg-amber-600/40"
            >
              <FolderOpen class="w-4 h-4" />
              <span>保存路径</span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'folders'" class="absolute top-full left-0 mt-2 w-72 bg-gray-800 rounded-lg border border-white/10 shadow-xl z-50 max-h-96 overflow-y-auto">
              <!-- 当前选中视频的 Folder -->
              <div class="p-3 border-b border-white/10">
                <span class="text-xs text-white/50 mb-1 block">当前选中视频的存储路径</span>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="f in selectedVideosFolders"
                    :key="f"
                    class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-amber-600/30 text-amber-200 border border-amber-500/30"
                  >
                    <Check class="w-3 h-3 mr-1" />
                    {{ f }}
                  </span>
                </div>
              </div>
              <div class="p-2 border-b border-white/10">
                <input
                  v-model="folderSearchQuery"
                  placeholder="筛选存储路径..."
                  class="w-full bg-gray-700/50 text-white text-sm px-3 py-1.5 rounded-lg border border-white/10 focus:outline-none focus:border-blue-500 placeholder-white/40"
                />
              </div>
              <div class="p-2 space-y-1">
                <div
                  v-for="folder in filteredFolderList"
                  :key="folder"
                  @click="onAssignFolderClick(folder)"
                  :class="[
                    'flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    selectedVideosFolders.includes(folder) ? 'bg-amber-600/20 text-amber-200' : 'hover:bg-white/5 text-white/80'
                  ]"
                >
                  <span class="text-sm">{{ folder }}</span>
                  <span class="text-xs text-white/50 bg-white/10 px-2 py-0.5 rounded-full">{{ getFolderCount(folder) }}</span>
                </div>
                <div v-if="availableFolders.length === 0" class="text-center py-4 text-white/40 text-sm">
                  暂无存储路径
                </div>
              </div>
            </div>
          </div>

          <!-- 标签分配下拉 -->
          <div class="relative">
            <button
              @click="showFilterPanel = showFilterPanel === 'tags' ? false : 'tags'"
              class="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-all border bg-emerald-600/30 border-emerald-500/50 text-emerald-200 hover:bg-emerald-600/40"
            >
              <Tag class="w-4 h-4" />
              <span>标签</span>
              <ChevronDown class="w-3 h-3" />
            </button>

            <div v-if="showFilterPanel === 'tags'" class="absolute top-full left-0 mt-2 w-72 bg-gray-800 rounded-lg border border-white/10 shadow-xl z-50 max-h-96 overflow-y-auto">
              <!-- 当前选中视频的标签 -->
              <div class="p-3 border-b border-white/10">
                <span class="text-xs text-white/50 mb-1 block">当前选中视频的标签</span>
                <div v-if="selectedVideosTags.length > 0" class="flex flex-wrap gap-1">
                  <span
                    v-for="tg in selectedVideosTags"
                    :key="tg"
                    :class="[
                      'inline-flex items-center px-2 py-0.5 rounded text-xs border',
                      commonSelectedTags.includes(tg)
                        ? 'bg-emerald-600/30 text-emerald-200 border-emerald-500/30'
                        : 'bg-amber-500/15 text-amber-200 border-amber-400/25',
                    ]"
                  >
                    <Check v-if="commonSelectedTags.includes(tg)" class="w-3 h-3 mr-1" />
                    {{ tg }}
                  </span>
                </div>
                <span v-else class="text-xs text-white/30">无标签</span>
              </div>
              <div class="p-2 border-b border-white/10">
                <input
                  v-model="tagSearchQuery"
                  placeholder="筛选标签..."
                  class="w-full bg-gray-700/50 text-white text-sm px-3 py-1.5 rounded-lg border border-white/10 focus:outline-none focus:border-blue-500 placeholder-white/40"
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
                      ? 'bg-rose-600/20 text-rose-200'
                      : selectedVideosTags.includes(tag)
                        ? 'bg-amber-500/15 text-amber-200'
                        : 'hover:bg-white/5 text-white/80'
                  ]"
                >
                  <div class="flex items-center gap-2">
                    <span class="text-sm">{{ tag }}</span>
                    <span
                      v-if="commonSelectedTags.includes(tag)"
                      class="rounded-full border border-rose-400/30 bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-medium text-rose-200"
                    >
                      点击移除
                    </span>
                    <span
                      v-else-if="selectedVideosTags.includes(tag)"
                      class="rounded-full border border-amber-400/25 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-200"
                    >
                      部分已拥有
                    </span>
                  </div>
                  <span class="text-xs text-white/50 bg-white/10 px-2 py-0.5 rounded-full">{{ getTagCount(tag) }}</span>
                </div>
                <div v-if="availableTags.length === 0" class="text-center py-4 text-white/40 text-sm">
                  暂无标签
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
          />
        </template>
      </div>

      <!-- 结果统计 -->
      <div class="flex flex-wrap items-center gap-3 text-sm text-white/50">
        <span>共 {{ filteredVideos.length }} 个视频，显示 {{ paginatedVideos.length }} 个</span>
        <span v-if="isSearching" class="text-cyan-200/80">搜索中...</span>
        <span v-else-if="activeSearchQuery" class="rounded-full border border-cyan-400/20 bg-cyan-500/10 px-2.5 py-1 text-cyan-100">
          {{ searchModeOptions.find(item => item.value === activeSearchMode)?.label || '搜索' }}:
          “{{ activeSearchQuery }}”
          <span class="ml-1 text-cyan-200/70">{{ searchTotalMatches }} 处匹配</span>
        </span>
        <span v-if="searchIsTruncated" class="text-amber-300/80">
          结果超过 2000 处匹配，已截断
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
        <Filter class="w-16 h-16 mx-auto mb-4 text-white/30" />
        <p class="text-white/60 text-lg mb-2">没有找到匹配的视频</p>
        <p class="text-white/40 text-sm mb-4">
          {{ activeSearchQuery ? '尝试更换关键词，或清空搜索与筛选条件' : '尝试调整筛选条件' }}
        </p>
        <div class="flex items-center justify-center gap-3">
          <button @click="clearFilters" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors">
            清除筛选
          </button>
          <button
            v-if="activeSearchQuery"
            @click="clearSearch"
            class="px-4 py-2 rounded-lg border border-white/15 bg-white/5 text-white/80 transition-colors hover:bg-white/10"
          >
            清空搜索
          </button>
        </div>
      </div>
    </div>

    <div v-else class="flex items-center justify-center py-12">
      <div class="text-center">
        <p class="text-white/60 text-lg mb-2">暂无视频</p>
        <p class="text-white/40 text-sm">请上传或添加视频</p>
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
              ? 'bg-gray-700/30 text-white/30 cursor-not-allowed'
              : 'bg-gray-700/50 text-white hover:bg-gray-600/50'
          ]"
        >
          上一页
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
                : 'bg-gray-700/50 text-white/70 hover:bg-gray-600/50'
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
              ? 'bg-gray-700/30 text-white/30 cursor-not-allowed'
              : 'bg-gray-700/50 text-white hover:bg-gray-600/50'
          ]"
        >
          下一页
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
        <div class="relative bg-[#1a1a2e] rounded-xl border border-white/10 shadow-2xl w-[420px] max-w-[90vw]">
          <!-- 标题栏 -->
          <div class="flex items-center justify-between p-5 pb-3">
            <h3 class="text-lg font-bold text-white">
              {{ confirmDialog.type === 'folder' ? '确认存储路径分配' : '确认标签分配' }}
            </h3>
            <button
              @click="confirmDialog.visible = false"
              class="w-8 h-8 rounded-full flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-colors"
            >
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- 内容 -->
          <div class="px-5 pb-5">
            <p class="text-green-400 text-sm leading-relaxed mb-6">
              <template v-if="confirmDialog.type === 'folder'">
                此操作将将存储路径"{{ confirmDialog.targetName }}"分配给 {{ selectedIds.length }} 选定的文档。
              </template>
              <template v-else>
                此操作将把标签"{{ confirmDialog.targetName }}"添加到 {{ selectedIds.length }} 个选定的文档。
              </template>
            </p>

            <!-- 按钮区 -->
            <div class="flex justify-end gap-3">
              <button
                @click="confirmDialog.visible = false"
                class="px-5 py-2 rounded-lg text-sm text-white/80 border border-white/20 hover:bg-white/10 transition-colors"
              >
                取消
              </button>
              <button
                @click="confirmAssign"
                class="px-5 py-2 rounded-lg text-sm text-black font-medium bg-amber-500 hover:bg-amber-400 transition-colors"
              >
                确认
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
