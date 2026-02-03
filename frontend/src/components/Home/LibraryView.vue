<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderOpen, Tag, Clock, FileText, Filter, SortAsc, ChevronDown, X } from 'lucide-vue-next'
import type { Video } from '@/types/media'
import VideoCard from '@/components/Home/VideoCard.vue'

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
}>()

// 筛选状态
const showFilterPanel = ref<false | 'folders' | 'tags' | 'types'>(false)
const filterMode = ref<'include' | 'exclude'>('include')
const selectedFolders = ref<string[]>([])
const selectedTags = ref<string[]>([])
const selectedTypes = ref<string[]>([])

// 排序状态
const sortBy = ref<'lastModified' | 'createdTime' | 'fileSize' | 'duration' | 'natural'>('lastModified')
const sortOrder = ref<'desc' | 'asc'>('desc')

// 分页状态
const currentPage = ref(1)
const itemsPerPage = ref(20)

// 获取所有文件夹（分类）- 从视频的 categoryName 字段提取
const availableFolders = computed(() => {
  const folders = new Set<string>()
  props.videos.forEach(v => {
    // 使用 categoryName 字段，如果没有则标记为"未分类"
    const folderName = v.categoryName || '未分类'
    folders.add(folderName)
  })
  return Array.from(folders).sort()
})

// 获取所有标签
const availableTags = computed(() => {
  const tags = new Set<string>()
  props.videos.forEach(v => {
    if (v.tags && Array.isArray(v.tags)) {
      v.tags.forEach(tag => tags.add(tag))
    }
  })
  return Array.from(tags).sort()
})

// 文件类型选项
const fileTypes = [
  { value: 'video', label: '视频', extensions: ['mp4', 'webm', 'mkv', 'avi', 'mov'] },
  { value: 'audio', label: '音频', extensions: ['mp3', 'm4a', 'wav', 'aac', 'flac'] },
]

// 排序选项
const sortOptions = [
  { value: 'lastModified', label: '最后访问时间' },
  { value: 'createdTime', label: '创建时间' },
  { value: 'fileSize', label: '文件大小' },
  { value: 'duration', label: '视频时长' },
  { value: 'natural', label: '自然排序' },
]

// 过滤视频
const filteredVideos = computed(() => {
  let result = [...props.videos]
  
  // 按文件夹筛选 - 使用 categoryName 字段
  if (selectedFolders.value.length > 0) {
    result = result.filter(v => {
      const folderName = v.categoryName || '未分类'
      const match = selectedFolders.value.includes(folderName)
      return filterMode.value === 'include' ? match : !match
    })
  }
  
  // 按标签筛选
  if (selectedTags.value.length > 0) {
    result = result.filter(v => {
      const videoTags = v.tags || []
      const match = selectedTags.value.some(tag => videoTags.includes(tag))
      return filterMode.value === 'include' ? match : !match
    })
  }
  
  // 按类型筛选
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

// 排序视频
const sortedVideos = computed(() => {
  const result = [...filteredVideos.value]
  
  result.sort((a, b) => {
    let comparison = 0
    
    switch (sortBy.value) {
      case 'lastModified':
        comparison = new Date(b.last_modified || 0).getTime() - new Date(a.last_modified || 0).getTime()
        break
      case 'createdTime':
        // 使用 file_created_time 字段（从文件系统获取的文件创建时间）
        comparison = new Date(b.file_created_time || 0).getTime() - new Date(a.file_created_time || 0).getTime()
        break
      case 'duration':
        // 优先使用后端返回的 video_length_seconds 字段
        const durationA = a.video_length_seconds || parseDuration(a.length)
        const durationB = b.video_length_seconds || parseDuration(b.length)
        comparison = durationB - durationA
        break
      case 'fileSize':
        // 使用后端返回的 file_size 字段（字节）
        comparison = (b.file_size || 0) - (a.file_size || 0)
        break
      case 'natural':
        // 自然排序：处理数字在字符串中的正确顺序（如 1,2,10 而非 1,10,2）
        comparison = a.name.localeCompare(b.name, undefined, { numeric: true })
        break
    }
    
    return sortOrder.value === 'asc' ? -comparison : comparison
  })
  
  return result
})

// 解析时长字符串为秒数
function parseDuration(duration: string | null | undefined): number {
  if (!duration) return 0
  
  // 格式: HH:MM:SS 或 MM:SS
  const parts = duration.split(':').map(Number)
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2]
  } else if (parts.length === 2) {
    return parts[0] * 60 + parts[1]
  }
  return 0
}

// 分页视频
const paginatedVideos = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value
  const end = start + itemsPerPage.value
  return sortedVideos.value.slice(start, end)
})

// 总页数
const totalPages = computed(() => {
  return Math.ceil(sortedVideos.value.length / itemsPerPage.value)
})

// 切换选中状态
function toggleSelection(id: number) {
  const newIds = props.selectedIds.includes(id)
    ? props.selectedIds.filter(i => i !== id)
    : [...props.selectedIds, id]
  emit('update:selectedIds', newIds)
}

// 切换文件夹选择
function toggleFolder(folder: string) {
  const index = selectedFolders.value.indexOf(folder)
  if (index > -1) {
    selectedFolders.value.splice(index, 1)
  } else {
    selectedFolders.value.push(folder)
  }
}

// 切换标签选择
function toggleTag(tag: string) {
  const index = selectedTags.value.indexOf(tag)
  if (index > -1) {
    selectedTags.value.splice(index, 1)
  } else {
    selectedTags.value.push(tag)
  }
}

// 切换类型选择
function toggleType(type: string) {
  const index = selectedTypes.value.indexOf(type)
  if (index > -1) {
    selectedTypes.value.splice(index, 1)
  } else {
    selectedTypes.value.push(type)
  }
}

// 清除所有筛选
function clearFilters() {
  selectedFolders.value = []
  selectedTags.value = []
  selectedTypes.value = []
}

// 获取文件夹视频数量 - 使用 categoryName 字段
function getFolderCount(folder: string): number {
  return props.videos.filter(v => {
    const videoFolder = v.categoryName || '未分类'
    return videoFolder === folder
  }).length
}

// 获取标签视频数量
function getTagCount(tag: string): number {
  return props.videos.filter(v => v.tags?.includes(tag)).length
}

// 监听筛选变化，重置页码
watch([selectedFolders, selectedTags, selectedTypes], () => {
  currentPage.value = 1
}, { deep: true })

// 监听排序变化
watch([sortBy, sortOrder], () => {
  currentPage.value = 1
})
</script>

<template>
  <div class="library-view">
    <!-- 顶部筛选栏 -->
    <div class="mb-6 space-y-4">
      <!-- 第一行：标题和排序 -->
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold text-white">{{ t('allMedia') }}</h2>
        
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
      
      <!-- 第二行：筛选按钮 -->
      <div class="flex items-center flex-wrap gap-2">
        <!-- 筛选模式切换 -->
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
        
        <!-- 文件夹筛选下拉 -->
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
          
          <!-- 文件夹下拉面板 - 暂时隐藏，因为 Video 类型没有 category 字段 -->
          <div v-if="showFilterPanel && showFilterPanel === 'folders'" class="absolute top-full left-0 mt-2 w-64 bg-gray-800 rounded-lg border border-white/10 shadow-xl z-50 max-h-80 overflow-y-auto">
            <div class="p-3 border-b border-white/10 flex items-center justify-between">
              <span class="text-sm font-medium text-white">选择文件夹</span>
              <button @click="selectedFolders = []" class="text-xs text-red-400 hover:text-red-300">清除</button>
            </div>
            <div class="p-2 space-y-1">
              <div 
                v-for="folder in availableFolders" 
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
        
        <!-- 标签筛选下拉 -->
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
          
          <!-- 标签下拉面板 -->
          <div v-if="showFilterPanel && showFilterPanel === 'tags'" class="absolute top-full left-0 mt-2 w-64 bg-gray-800 rounded-lg border border-white/10 shadow-xl z-50 max-h-80 overflow-y-auto">
            <div class="p-3 border-b border-white/10 flex items-center justify-between">
              <span class="text-sm font-medium text-white">选择标签</span>
              <button @click="selectedTags = []" class="text-xs text-red-400 hover:text-red-300">清除</button>
            </div>
            <div class="p-2 space-y-1">
              <div 
                v-for="tag in availableTags" 
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
          
          <!-- 类型下拉面板 -->
          <div v-if="showFilterPanel && showFilterPanel === 'types'" class="absolute top-full left-0 mt-2 w-48 bg-gray-800 rounded-lg border border-white/10 shadow-xl z-50">
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
        
        <!-- 清除所有筛选 -->
        <button 
          v-if="selectedFolders.length > 0 || selectedTags.length > 0 || selectedTypes.length > 0"
          @click="clearFilters"
          class="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm bg-red-600/20 border border-red-500/30 text-red-300 hover:bg-red-600/30 transition-colors"
        >
          <X class="w-4 h-4" />
          <span>清除筛选</span>
        </button>
      </div>
      
      <!-- 结果统计 -->
      <div class="text-sm text-white/50">
        共 {{ filteredVideos.length }} 个视频，显示 {{ paginatedVideos.length }} 个
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
        <p class="text-white/40 text-sm mb-4">尝试调整筛选条件</p>
        <button @click="clearFilters" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors">
          清除筛选
        </button>
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
  </div>
</template>

<style scoped>
.library-view {
  @apply w-full;
}

/* 自定义滚动条 */
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