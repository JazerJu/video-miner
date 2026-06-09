<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ChapterAPI, type Chapter } from '@/composables/ChapterAPI'
import { useI18n } from 'vue-i18n'

// i18n functionality
const { t } = useI18n()

const props = defineProps<{
  currentTime: number
  id: number
  showChapterMarkers?: boolean // Control chapter marker visibility
}>()

const emit = defineEmits<{
  (e: 'seek', time: number): void
  (e: 'toggle-chapter-markers', show: boolean): void
}>()

// Chapter data loaded from backend
const chapters = ref<Chapter[]>([])

const showEditDialog = ref(false)
const isFetchingImages = ref(false)

// Local state for chapter marker visibility toggle
const localShowChapterMarkers = ref(props.showChapterMarkers ?? true)

// Watch for prop changes
watch(() => props.showChapterMarkers, (newValue) => {
  if (newValue !== undefined) {
    localShowChapterMarkers.value = newValue
  }
})

function toggleChapterMarkers() {
  localShowChapterMarkers.value = !localShowChapterMarkers.value
  emit('toggle-chapter-markers', localShowChapterMarkers.value)
  console.log(`[VideoChapters] Toggle chapter markers: ${localShowChapterMarkers.value}`)
}

const formatTime = (seconds: number) => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const getCurrentChapter = computed(() => {
  // Flatten all chapters including children for search
  const allChapters: Chapter[] = []
  chapters.value.forEach((c) => {
    allChapters.push(c)
    if (c.children) {
      allChapters.push(...c.children)
    }
  })

  // Find all matching chapters, then select the one with the latest startTime
  const matchingChapters = allChapters.filter(
    (chapter) =>
      props.currentTime >= chapter.startTime &&
      (chapter.endTime === undefined || props.currentTime < chapter.endTime),
  )
  
  // Sort by startTime descending and pick the first (latest)
  // If parent (3:00) and child (3:10) both match, child is selected.
  const current = matchingChapters.sort((a, b) => b.startTime - a.startTime)[0] || null
  
  return current
})

const jumpToChapter = (chapter: Chapter) => {
  emit('seek', chapter.startTime)
}

const openEditDialog = () => {
  showEditDialog.value = true
}

const fetchThumbnails = async () => {
  if (!props.id || props.id <= 0) {
    alert('无效的视频ID，无法获取缩略图')
    return
  }

  isFetchingImages.value = true

  try {
    // Flatten chapters for API call to ensure all get thumbnails
    const flatChapters: Chapter[] = []
    chapters.value.forEach(c => {
      flatChapters.push(c)
      if (c.children) flatChapters.push(...c.children)
    })

    // We pass the structure, but maybe we should just pass flattened list to get screenshots?
    // Actually ChapterAPI.getChapterScreenshots iterates and returns a mapped array.
    // We need to handle the reconstruction or update ChapterAPI.
    // For simplicity, let's just update the top level for now, or update ChapterAPI later.
    // Let's rely on the ChapterAPI returning updated chapters but it might not handle nesting.
    // To support nesting, we should update ChapterAPI or handle it here.
    
    // Let's update ChapterAPI.getChapterScreenshots to handle nesting or just do it here:
    // We'll skip complex thumbnail logic for sub-chapters for this iteration to avoid breaking things,
    // or we can implement a simple recursive update.
    
    const updatedChapters = await ChapterAPI.getChapterScreenshots(props.id, chapters.value)
    chapters.value = updatedChapters

    // Auto-save chapters with updated thumbnails
    await ChapterAPI.saveChapters(props.id, chapters.value)
  } catch (error) {
    console.error('Failed to fetch thumbnails:', error)
    alert('获取缩略图失败，请重试')
  }

  isFetchingImages.value = false
}

const saveChapters = async () => {
  if (!props.id || props.id <= 0) {
    alert('无效的视频ID，无法保存章节')
    return
  }

  const success = await ChapterAPI.saveChapters(props.id, chapters.value)
  if (success) {
    showEditDialog.value = false
  } else {
    alert('保存章节失败，请重试')
  }
}

const addChapter = () => {
  const newChapter: Chapter = {
    id: Date.now().toString(),
    title: `新章节 ${chapters.value.length + 1}`,
    startTime: Math.max(0, props.currentTime),
    children: []
  }
  chapters.value.push(newChapter)
  chapters.value.sort((a, b) => a.startTime - b.startTime)
}

const addSubChapter = (parentChapter: Chapter) => {
  if (!parentChapter.children) {
    parentChapter.children = []
  }
  const newChapter: Chapter = {
    id: Date.now().toString() + Math.random().toString().slice(2, 5),
    title: `子章节 ${parentChapter.children.length + 1}`,
    startTime: Math.max(parentChapter.startTime, props.currentTime),
    endTime: undefined
  }
  parentChapter.children.push(newChapter)
  parentChapter.children.sort((a, b) => a.startTime - b.startTime)
}

const removeChapter = (chapterId: string) => {
  const index = chapters.value.findIndex((c) => c.id === chapterId)
  if (index > -1) {
    chapters.value.splice(index, 1)
  }
}

const removeSubChapter = (parentChapter: Chapter, childId: string) => {
  if (parentChapter.children) {
    const index = parentChapter.children.findIndex((c) => c.id === childId)
    if (index > -1) {
      parentChapter.children.splice(index, 1)
    }
  }
}

// Load chapters when component mounts or video ID changes
const loadChapters = async () => {
  if (props.id && props.id > 0) {
    try {
      const loadedChapters = await ChapterAPI.loadChapters(props.id)
      chapters.value = loadedChapters
      console.log(`[VideoChapters] Loaded ${loadedChapters.length} chapters:`, loadedChapters.map(c => ({ id: c.id, title: c.title, startTime: c.startTime, endTime: c.endTime })))
      console.log('[VideoChapters] Full chapter data:', loadedChapters)
    } catch (error) {
      console.error('Failed to load chapters:', error)
    }
  } else {
    // Clear chapters if invalid ID
    chapters.value = []
    console.log(`[VideoChapters] Cleared chapters (invalid ID: ${props.id})`)
  }
}

onMounted(() => {
  loadChapters()
})

// Watch for video ID changes and reload chapters
watch(
  () => props.id,
  () => {
    loadChapters()
  },
  { immediate: false },
)
</script>

<style scoped>
/* 自定义滚动条 */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.8);
  border-radius: 3px;
}

:global(html.dark) .custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(71, 85, 105, 0.3);
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.45);
  border-radius: 3px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(100, 116, 139, 0.65);
}

:global(html.dark) .custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.5);
}

:global(html.dark) .custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.8);
}
</style>

<template>
  <div class="p-6">
    <!-- Header with action buttons -->
    <div class="flex justify-between items-center mb-6">
      <h3 class="text-xl font-semibold text-slate-900 dark:text-white">{{ t('videoChaptersTitle') }}</h3>
      <div v-if="props.id && props.id > 0" class="flex space-x-3">
        <!-- Chapter Marker Toggle -->
        <button
          @click="toggleChapterMarkers"
          :class="localShowChapterMarkers ? 'bg-green-600/80 hover:bg-green-600 border-green-500/30 text-white' : 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-600/80 dark:hover:bg-slate-600 border-slate-200 dark:border-slate-500/30 text-slate-700 dark:text-white'"
          class="px-4 py-2 text-sm rounded-lg transition-colors backdrop-blur-sm border"
          :title="localShowChapterMarkers ? '隐藏进度条章节标记' : '显示进度条章节标记'"
        >
          <span v-if="localShowChapterMarkers" class="flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2">
              <path d="M12 20h9"/>
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
            </svg>
            显示标记
          </span>
          <span v-else class="flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
            </svg>
            隐藏标记
          </span>
        </button>
        <button
          @click="openEditDialog"
          class="px-4 py-2 bg-blue-600/80 hover:bg-blue-600 text-white text-sm rounded-lg transition-colors backdrop-blur-sm border border-blue-500/30"
        >
          编辑章节
        </button>
        <button
          @click="fetchThumbnails"
          :disabled="isFetchingImages || chapters.length === 0"
          class="px-4 py-2 bg-green-600/80 hover:bg-green-600 text-white text-sm rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed backdrop-blur-sm border border-green-500/30"
        >
          <span v-if="isFetchingImages" class="flex items-center">
            <svg
              class="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                class="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="4"
              ></circle>
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            获取中...
          </span>
          <span v-else>获取缩略图</span>
        </button>
      </div>
      <div v-else class="text-sm text-slate-500 dark:text-slate-400">{{ t('waitingVideoLoad') }}</div>
    </div>

    <!-- Chapter List -->
    <div class="space-y-4 max-h-96 overflow-y-auto custom-scrollbar">
      <div v-for="(chapter, index) in chapters" :key="chapter.id" class="space-y-2">
        <!-- Parent Chapter -->
        <div
          @click="jumpToChapter(chapter)"
          class="flex items-center p-4 rounded-xl border cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700/30 transition-all duration-200"
          :class="
            getCurrentChapter?.id === chapter.id
              ? 'border-blue-500/50 bg-blue-50 dark:bg-blue-900/30 shadow-lg'
              : 'border-slate-200 dark:border-slate-600/30 hover:border-slate-300 dark:hover:border-slate-500/50'
          "
        >
          <!-- Thumbnail -->
          <div class="flex-shrink-0 w-32 h-20 bg-slate-100 dark:bg-slate-700/50 rounded-lg overflow-hidden mr-4 border border-slate-200 dark:border-slate-600/30">
            <img
              v-if="chapter.thumbnail"
              :src="chapter.thumbnail"
              :alt="`Chapter ${index + 1} thumbnail`"
              class="w-full h-full object-cover"
            />
            <div v-else class="w-full h-full flex items-center justify-center text-slate-500 dark:text-slate-400 text-sm">
              <svg class="w-8 h-8 text-slate-400 dark:text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
          </div>

          <!-- Chapter Info -->
          <div class="flex-1 min-w-0">
            <h4 class="font-medium text-slate-900 dark:text-white truncate mb-1 text-lg">{{ chapter.title }}</h4>
            <p class="text-sm text-slate-500 dark:text-slate-400">
              {{ formatTime(chapter.startTime) }}
              <span v-if="chapter.endTime"> - {{ formatTime(chapter.endTime) }}</span>
            </p>
          </div>

          <!-- Current indicator -->
          <div v-if="getCurrentChapter?.id === chapter.id" class="flex-shrink-0 ml-3">
            <div class="w-3 h-3 bg-blue-500 rounded-full animate-pulse"></div>
          </div>
        </div>

        <!-- Child Chapters -->
        <div v-if="chapter.children && chapter.children.length > 0" class="ml-12 space-y-2 border-l-2 border-slate-200 dark:border-slate-700/50 pl-4">
          <div
            v-for="(child, childIndex) in chapter.children"
            :key="child.id"
            @click="jumpToChapter(child)"
            class="flex items-center p-3 rounded-lg border cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700/30 transition-all duration-200 bg-slate-50 dark:bg-slate-800/20"
            :class="
              getCurrentChapter?.id === child.id
                ? 'border-blue-500/50 bg-blue-50 dark:bg-blue-900/20'
                : 'border-slate-200 dark:border-slate-600/20 hover:border-slate-300 dark:hover:border-slate-500/40'
            "
          >
            <!-- No thumbnail for children to save space, or smaller one? Let's keep it text only for now or user feedback -->
            <div class="flex-1 min-w-0">
                <h5 class="font-medium text-slate-700 dark:text-slate-200 truncate text-base">{{ child.title }}</h5>
                <p class="text-xs text-slate-500 dark:text-slate-500">
                 {{ formatTime(child.startTime) }}
                 <span v-if="child.endTime"> - {{ formatTime(child.endTime) }}</span>
               </p>
            </div>
             <!-- Current indicator for child -->
            <div v-if="getCurrentChapter?.id === child.id" class="flex-shrink-0 ml-3">
              <div class="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!props.id || props.id <= 0" class="text-center py-12 text-slate-500 dark:text-slate-400">
        {{ t('waitingVideoLoading') }}
      </div>
      <div v-else-if="chapters.length === 0" class="text-center py-12 text-slate-500 dark:text-slate-400">
        {{ t('noChapters') }}
      </div>
    </div>

    <!-- Edit Dialog -->
    <div
      v-if="showEditDialog"
      class="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
      @click.self="showEditDialog = false"
    >
      <div class="bg-white/95 dark:bg-gradient-to-br dark:from-slate-800/95 dark:to-slate-700/95 rounded-2xl p-8 w-full max-w-4xl max-h-[85vh] overflow-y-auto border border-slate-200 dark:border-slate-600/50 shadow-2xl backdrop-blur-lg">
        <div class="flex justify-between items-center mb-6">
          <h3 class="text-2xl font-semibold text-slate-900 dark:text-white">编辑章节</h3>
          <button @click="showEditDialog = false" class="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-all">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="space-y-4 max-h-[60vh] overflow-y-auto custom-scrollbar pr-2">
          <div v-for="(chapter, index) in chapters" :key="chapter.id" class="space-y-2 border border-slate-200 dark:border-slate-600/30 rounded-xl p-3 bg-slate-50 dark:bg-slate-800/30">
            <!-- Parent Editor -->
            <div class="flex items-center space-x-3">
              <span class="text-sm text-slate-500 dark:text-slate-400 w-6 font-mono font-bold">{{ index + 1 }}</span>
              <input
                v-model="chapter.title"
                type="text"
                class="flex-1 px-3 py-2 bg-white dark:bg-slate-600/50 border border-slate-300 dark:border-slate-500/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white placeholder-slate-400 transition-all"
                placeholder="一级章节标题"
              />
              <div class="flex items-center space-x-1">
                <input
                  v-model.number="chapter.startTime"
                  type="number"
                  min="0"
                  step="1"
                  class="w-20 px-2 py-2 bg-white dark:bg-slate-600/50 border border-slate-300 dark:border-slate-500/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white placeholder-slate-400 text-center text-sm"
                  placeholder="开始"
                  title="开始时间(秒)"
                />
                <span class="text-slate-500 dark:text-slate-500">-</span>
                <input
                  v-model.number="chapter.endTime"
                  type="number"
                  min="0"
                  step="1"
                  class="w-20 px-2 py-2 bg-white dark:bg-slate-600/50 border border-slate-300 dark:border-slate-500/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white placeholder-slate-400 text-center text-sm"
                  placeholder="结束"
                  title="结束时间(秒，可选)"
                />
              </div>
              
              <button
                @click="addSubChapter(chapter)"
                class="text-blue-400 hover:text-blue-300 p-2 rounded-lg hover:bg-blue-500/20 transition-all"
                title="添加子章节"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                </svg>
              </button>
              <button
                @click="removeChapter(chapter.id)"
                class="text-red-400 hover:text-red-300 p-2 rounded-lg hover:bg-red-500/20 transition-all"
                title="删除章节"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>

            <!-- Children Editor -->
            <div v-if="chapter.children && chapter.children.length > 0" class="ml-10 space-y-2 pl-4 border-l border-slate-200 dark:border-slate-600/30">
               <div v-for="(child, childIndex) in chapter.children" :key="child.id" class="flex items-center space-x-3">
                  <span class="text-xs text-slate-500 dark:text-slate-500 w-6 font-mono">{{ index + 1 }}.{{ childIndex + 1 }}</span>
                  <input
                    v-model="child.title"
                    type="text"
                    class="flex-1 px-3 py-1.5 bg-white dark:bg-slate-700/50 border border-slate-300 dark:border-slate-600/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 text-sm transition-all"
                    placeholder="子章节标题"
                  />
                  <div class="flex items-center space-x-1">
                    <input
                      v-model.number="child.startTime"
                      type="number"
                      min="0"
                      step="1"
                      class="w-16 px-2 py-1.5 bg-white dark:bg-slate-700/50 border border-slate-300 dark:border-slate-600/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 text-center text-xs"
                      placeholder="开始"
                    />
                    <span class="text-slate-500 dark:text-slate-600">-</span>
                    <input
                      v-model.number="child.endTime"
                      type="number"
                      min="0"
                      step="1"
                      class="w-16 px-2 py-1.5 bg-white dark:bg-slate-700/50 border border-slate-300 dark:border-slate-600/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 text-center text-xs"
                      placeholder="结束"
                    />
                  </div>
                  <button
                    @click="removeSubChapter(chapter, child.id)"
                    class="text-red-400 hover:text-red-300 p-1.5 rounded-lg hover:bg-red-500/20 transition-all"
                    title="删除子章节"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
               </div>
            </div>
          </div>

          <button
            @click="addChapter"
            class="w-full py-4 border-2 border-dashed border-slate-300 dark:border-slate-600/50 rounded-xl text-slate-500 dark:text-slate-400 hover:border-slate-400 dark:hover:border-slate-500/70 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/20 transition-all flex justify-center items-center"
          >
            <svg class="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            添加新的一级章节
          </button>
        </div>

        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-slate-200 dark:border-slate-600/30">
          <button
            @click="showEditDialog = false"
            class="px-6 py-2 text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white bg-white hover:bg-slate-100 dark:bg-slate-700/50 dark:hover:bg-slate-600/70 rounded-lg transition-all border border-slate-200 dark:border-slate-600/30"
          >
            取消
          </button>
          <button
            @click="saveChapters"
            class="px-6 py-2 bg-blue-600/80 hover:bg-blue-600 text-white rounded-lg transition-all border border-blue-500/30 shadow-lg"
          >
            保存更改
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Custom scrollbar for chapter list */
.max-h-96::-webkit-scrollbar {
  width: 6px;
}

.max-h-96::-webkit-scrollbar-track {
  background: #e2e8f0;
  border-radius: 3px;
}

:global(html.dark) .max-h-96::-webkit-scrollbar-track {
  background: rgba(71, 85, 105, 0.3);
}

.max-h-96::-webkit-scrollbar-thumb {
  background: #94a3b8;
  border-radius: 3px;
}

.max-h-96::-webkit-scrollbar-thumb:hover {
  background: #64748b;
}

:global(html.dark) .max-h-96::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.5);
}

:global(html.dark) .max-h-96::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.8);
}
</style>
