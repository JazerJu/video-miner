<!-- 字幕面板 -->
<script setup lang="ts">
import type { Subtitle } from '@/types/subtitle'
import { useSubtitles } from '@/composables/useSubtitles'
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import { blobUrls, generateVTT } from '@/composables/Buildvtt'
import { MoreHorizontal, Upload, Sparkles } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import EnhancedSubtitleDialog from '@/components/dialogs/EnhancedSubtitleDialog.vue'
import { ChapterAPI, type Chapter } from '@/composables/ChapterAPI'
import { loadConfig } from '@/composables/ConfigAPI'

const {
  parseSRT,
  // downloadSubtitles,
  linkSubtitles,
  fetchSubtitle,
} = useSubtitles()

// parse & read subtitles
const uploadSubtitles = (event: Event): void => {
  const input = event.target as HTMLInputElement // Get precise type
  const file = input.files?.[0]
  if (!file) return

  const reader = new FileReader()

  reader.onload = (e) => {
    const result = (e.target as FileReader).result
    if (typeof result !== 'string') return

    let subtitles = parseSRT(result)
    console.log(subtitles)
    if (confirm('字幕已成功解析，是否要上传到服务器？')) {
      // 根据当前切换状态决定使用哪种语言
      let targetLang: string
      let targetSubtitles: typeof subtitles

      if (showTranslationProxy.value) {
        // 翻译模式：使用用户界面语言
        targetLang = userInterfaceLanguage.value
        console.log(`上传翻译字幕，语言: ${targetLang}`)
      } else {
        // 原文模式：使用视频原始语言
        if (!props.rawLang) {
          ElMessage.warning('视频的原始语言未设置，请先设置语言')
          // 打开语言设置对话框
          showEnhancedSubtitleDialog.value = true
          return
        }
        targetLang = props.rawLang
        console.log(`上传原文字幕，语言: ${targetLang}`)
      }

      linkSubtitles(props.id, targetLang, subtitles)
    }
  }

  reader.readAsText(file)
}

// 使用v-model代理，保持与TabbedPanel的状态同步
const showTranslationProxy = computed({
  get: () => props.showTranslation ?? false,
  set: (value: boolean) => emit('update:showTranslation', value),
})
const autoScroll = ref(false)
const compactMode = ref(false)

// Enhanced subtitle dialog state
const showEnhancedSubtitleDialog = ref(false)

const props = defineProps<{
  currentTime: number
  id: number
  rawLang?: string
  videoName?: string
  showTranslation?: boolean
}>()

const emit = defineEmits<{
  (e: 'seek', time: number): void
  (e: 'update-bloburls', blobUrls: Array<string | undefined>): void
  (e: 'update:showTranslation', value: boolean): void
}>()

function isActive(s: Subtitle) {
  return props.currentTime >= s.start && props.currentTime <= s.end
}

const formatTime = (seconds: number) => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const subtitles = ref<Subtitle[]>([]) // 原文字幕
const foreignSub = ref<Subtitle[]>([])
const chapters = ref<Chapter[]>([]) // 章节数据
const userInterfaceLanguage = ref<string>('zh') // 用户界面语言设置
const isLoadingSubtitles = ref(false) // 防止在加载过程中触发watch handlers的竞态条件

// 加载章节数据
const loadChapters = async () => {
  if (props.id && props.id > 0) {
    try {
      chapters.value = await ChapterAPI.loadChapters(props.id)
      console.log('[SubtitlePanel] Loaded chapters:', chapters.value)
    } catch (error) {
      console.error('[SubtitlePanel] Failed to load chapters:', error)
      chapters.value = []
    }
  } else {
    chapters.value = []
  }
}

onMounted(async () => {
  // Load user's interface language preference
  try {
    const config = await loadConfig()
    userInterfaceLanguage.value = config.defaultTranslateLang || 'zh'
  } catch (error) {
    console.warn('Failed to load user config, using default zh:', error)
    userInterfaceLanguage.value = 'zh'
  }

  // Load compact mode preference from localStorage
  try {
    const savedCompactMode = localStorage.getItem('subtitleCompactMode')
    if (savedCompactMode !== null) {
      compactMode.value = savedCompactMode === 'true'
    }
  } catch (error) {
    console.warn('Failed to load compact mode preference:', error)
  }

  // Set loading state to prevent race conditions
  isLoadingSubtitles.value = true

  // Use video's rawLang or fallback to 'zh' (consistent with watch function)
  const primaryLang = props.rawLang || 'zh'
  // Use user's interface language preference for translation
  const foreignLang = userInterfaceLanguage.value
  console.log('props.rawLang is ', props.rawLang)
  console.log('primaryLang is ', primaryLang)
  console.log('foreignLang (user preference) is ', foreignLang)

  // 原文字幕 (use video's language)
  try {
    subtitles.value = await fetchSubtitle(props.id, primaryLang)
    console.log('Primary subtitles loaded:', subtitles.value.length, 'items')
  } catch (error) {
    console.warn(`Primary subtitles (${primaryLang}) not found:`, error)
    subtitles.value = []
  }

  // 外文字幕 (use user's preferred language for translation)
  try {
    foreignSub.value = await fetchSubtitle(props.id, foreignLang)
    console.log('Translation subtitles loaded:', foreignSub.value.length, 'items')
  } catch (error) {
    console.warn(`Translation subtitles (${foreignLang}) not found:`, error)
    foreignSub.value = []
  }

  // 加载章节数据
  await loadChapters()

  // Generate VTT files only for available subtitles
  blobUrls.value[0] =
    subtitles.value.length > 0 ? generateVTT('primary', [subtitles.value]) : undefined
  blobUrls.value[1] =
    foreignSub.value.length > 0 ? generateVTT('translation', [foreignSub.value]) : undefined
  blobUrls.value[2] =
    subtitles.value.length > 0 && foreignSub.value.length > 0
      ? generateVTT('both', [subtitles.value, foreignSub.value])
      : undefined

  console.log('Final blobUrls for video ID', props.id, ':', {
    primary: !!blobUrls.value[0],
    translation: !!blobUrls.value[1],
    both: !!blobUrls.value[2],
  })

  // Debug: log first few characters of each subtitle to verify correct content
  if (subtitles.value.length > 0) {
    console.log('Primary subtitle sample:', subtitles.value[0]?.text.substring(0, 30) + '...')
  }
  if (foreignSub.value.length > 0) {
    console.log('Translation subtitle sample:', foreignSub.value[0]?.text.substring(0, 30) + '...')
  }

  // Clear loading state - both subtitle arrays are now synchronized
  isLoadingSubtitles.value = false

  // Emit initial update to parent component
  emit('update-bloburls', blobUrls.value)
})

// Prop Id变化，随之获取Subtitle的数值。
watch(
  () => props.id,
  async (id) => {
    // Set loading state to prevent race conditions
    isLoadingSubtitles.value = true

    const primaryLang = props.rawLang || 'zh'
    const foreignLang = userInterfaceLanguage.value

    // Load primary subtitles
    try {
      subtitles.value = await fetchSubtitle(id, primaryLang)
      console.log(
        `[Watch] Primary subtitles (${primaryLang}) loaded:`,
        subtitles.value.length,
        'items',
      )
    } catch (error) {
      console.warn(`[Watch] Primary subtitles (${primaryLang}) not found:`, error)
      subtitles.value = []
    }

    // Load translation subtitles
    try {
      foreignSub.value = await fetchSubtitle(id, foreignLang)
      console.log(
        `[Watch] Translation subtitles (${foreignLang}) loaded:`,
        foreignSub.value.length,
        'items',
      )
    } catch (error) {
      console.warn(`[Watch] Translation subtitles (${foreignLang}) not found:`, error)
      foreignSub.value = []
    }

    // 重新加载章节数据
    await loadChapters()

    // Update blobUrls based on available subtitles
    blobUrls.value[0] =
      subtitles.value.length > 0 ? generateVTT('primary', [subtitles.value]) : undefined
    blobUrls.value[1] =
      foreignSub.value.length > 0 ? generateVTT('translation', [foreignSub.value]) : undefined
    blobUrls.value[2] =
      subtitles.value.length > 0 && foreignSub.value.length > 0
        ? generateVTT('both', [subtitles.value, foreignSub.value])
        : undefined

    console.log('[Watch] Updated blobUrls for video ID', id, ':', {
      primary: !!blobUrls.value[0],
      translation: !!blobUrls.value[1],
      both: !!blobUrls.value[2],
    })

    // Debug: log first few characters of each subtitle to verify correct content
    if (subtitles.value.length > 0) {
      console.log(
        '[Watch] Primary subtitle sample:',
        subtitles.value[0]?.text.substring(0, 30) + '...',
      )
    }
    if (foreignSub.value.length > 0) {
      console.log(
        '[Watch] Translation subtitle sample:',
        foreignSub.value[0]?.text.substring(0, 30) + '...',
      )
    }

    // Clear loading state - both subtitle arrays are now synchronized
    isLoadingSubtitles.value = false

    // Emit the update to parent component
    emit('update-bloburls', blobUrls.value)
  },
)
watch(
  () => subtitles.value,
  (newRaw, oldRaw) => {
    // 防止在加载新视频过程中触发此处理器，避免使用过时的foreignSub数据
    if (isLoadingSubtitles.value) {
      console.log('[Watch] Skipping subtitles watch handler - loading in progress')
      return
    }

    if (oldRaw && blobUrls.value[0]) URL.revokeObjectURL(blobUrls.value[0])

    blobUrls.value[0] = newRaw.length > 0 ? generateVTT('primary', [newRaw]) : undefined
    blobUrls.value[2] =
      newRaw.length > 0 && foreignSub.value.length > 0
        ? generateVTT('both', [newRaw, foreignSub.value])
        : undefined

    console.log('[Watch] Primary subtitles changed, updating blobUrls')
    emit('update-bloburls', blobUrls.value)
  },
  { deep: true },
)

// 用于实现文本的自动滚动 //
// ① 用数组收集 v-for 产生的行元素
const rowRefs = ref<(HTMLElement | null)[]>([])
// 字幕列表容器的 ref
const subtitlesContainerRef = ref<HTMLElement | null>(null)

// 计算全局字幕索引（考虑章节分组）
const globalActiveIndex = computed(() => {
  const currentSubs = showTranslationProxy.value ? foreignSub.value : subtitles.value
  const activeSubtitle = currentSubs.find(isActive)
  if (!activeSubtitle) return -1

  // 在分组中找到全局索引
  let globalIndex = 0
  for (const group of subtitlesByChapter.value) {
    const subIndex = group.subtitles.findIndex(
      (s) => s.start === activeSubtitle.start && s.text === activeSubtitle.text,
    )
    if (subIndex !== -1) {
      return globalIndex + subIndex
    }
    globalIndex += group.subtitles.length
  }
  return -1
})

// ③ 当活动索引变化 ⇒ 仅在容器内部滚动，不影响页面
let scrollTimeout: ReturnType<typeof setTimeout> | null = null

// Watch compact mode changes and save to localStorage
watch(compactMode, (newValue) => {
  try {
    localStorage.setItem('subtitleCompactMode', newValue.toString())
  } catch (error) {
    console.warn('Failed to save compact mode preference:', error)
  }
})

watch(globalActiveIndex, (idx, oldIdx) => {
  if (!autoScroll.value || idx === -1 || idx === oldIdx) return

  // Clear previous scroll timeout to prevent multiple scroll operations
  if (scrollTimeout) {
    clearTimeout(scrollTimeout)
  }

  // Debounce scroll operations to make them smoother
  scrollTimeout = setTimeout(() => {
    nextTick(() => {
      const container = subtitlesContainerRef.value
      const el = rowRefs.value[idx]
      if (!container || !el) return

      // 计算元素相对于容器的偏移位置
      const containerRect = container.getBoundingClientRect()
      const elRect = el.getBoundingClientRect()

      // 计算元素在容器内的相对位置
      const elRelativeTop = elRect.top - containerRect.top + container.scrollTop

      // 计算居中滚动位置：元素顶部 - 容器高度的一半 + 元素高度的一半
      const scrollTop = elRelativeTop - containerRect.height / 2 + elRect.height / 2

      // 仅滚动容器内部，不影响页面
      container.scrollTo({
        top: Math.max(0, scrollTop),
        behavior: 'smooth',
      })
    })
  }, 100) // 100ms debounce delay
})

// 根据章节分组字幕
const subtitlesByChapter = computed(() => {
  const currentSubs = showTranslationProxy.value ? foreignSub.value : subtitles.value

  if (chapters.value.length === 0) {
    // 如果没有章节，返回所有字幕作为一个组
    return [{ chapter: null, subtitles: currentSubs }]
  }

  // 按章节分组字幕
  const groups: Array<{ chapter: Chapter | null; subtitles: Subtitle[] }> = []

  // 按开始时间排序章节
  const sortedChapters = [...chapters.value].sort((a, b) => a.startTime - b.startTime)

  for (let i = 0; i < sortedChapters.length; i++) {
    const chapter = sortedChapters[i]
    const nextChapter = sortedChapters[i + 1]

    // 获取当前章节的字幕（从章节开始时间到下一章节开始时间，或到视频结束）
    const chapterSubtitles = currentSubs.filter((sub) => {
      const isAfterStart = sub.start >= chapter.startTime
      const isBeforeNext = !nextChapter || sub.start < nextChapter.startTime
      return isAfterStart && isBeforeNext
    })

    groups.push({ chapter, subtitles: chapterSubtitles })
  }

  // 处理在第一个章节之前的字幕
  if (sortedChapters.length > 0) {
    const firstChapter = sortedChapters[0]
    const beforeFirstChapter = currentSubs.filter((sub) => sub.start < firstChapter.startTime)

    if (beforeFirstChapter.length > 0) {
      groups.unshift({ chapter: null, subtitles: beforeFirstChapter })
    }
  }

  return groups
})

// Handle enhanced subtitle dialog submission
function handleSubtitleDialogSubmitted() {
  // Refresh subtitles or perform any necessary updates
  console.log('Subtitle dialog submitted, refreshing...')
}
</script>

<template>
  <div class="p-6">
    <!-- Control Bar -->
    <div
      class="flex items-center justify-between mb-6 p-4 bg-slate-700/30 rounded-xl border border-slate-600/30"
    >
      <!-- Left Side Controls -->
      <div class="flex items-center space-x-4">
        <!-- Auto Scroll Checkbox -->
        <el-checkbox v-model="autoScroll" class="blue-checkbox">
          <span class="text-slate-300">自动滚动</span>
        </el-checkbox>
      </div>

      <!-- Action Buttons (Right) -->
      <div class="flex items-center space-x-3">
        <!-- Generate Subtitle Button -->
        <el-button
          @click="showEnhancedSubtitleDialog = true"
          size="small"
          type="primary"
          class="!bg-green-600 !border-green-600 hover:!bg-green-700"
        >
          <Sparkles class="w-4 h-4 mr-1" />
          字幕操作
        </el-button>

        <!-- More Options Dropdown -->
        <el-dropdown trigger="click">
          <el-button size="small" class="!bg-slate-600 !border-slate-600 hover:!bg-slate-700">
            <MoreHorizontal class="w-4 h-4" />
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <!-- File Upload Option -->
              <el-dropdown-item>
                <label class="flex items-center cursor-pointer w-full">
                  <Upload class="w-4 h-4 mr-2" />
                  <span>上传字幕文件</span>
                  <input
                    type="file"
                    @change="(e) => uploadSubtitles(e)"
                    accept=".srt,.vtt"
                    class="hidden"
                  />
                </label>
              </el-dropdown-item>

               <!-- Language Toggle Option -->
               <el-dropdown-item>
                 <div class="flex items-center space-x-3">
                   <span class="text-sm text-slate-600 font-medium">原文</span>
                   <el-switch
                     v-model="showTranslationProxy"
                     active-color="#3b82f6"
                     inactive-color="#475569"
                     size="small"
                   />
                   <span class="text-sm text-slate-600 font-medium">翻译</span>
                 </div>
               </el-dropdown-item>

               <!-- Compact Mode Toggle Option -->
               <el-dropdown-item>
                 <div class="flex items-center justify-between w-full">
                   <span class="text-sm text-slate-600 font-medium">紧凑模式</span>
                   <el-switch
                     v-model="compactMode"
                     active-color="#10b981"
                     inactive-color="#475569"
                     size="small"
                   />
                 </div>
               </el-dropdown-item>
             </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- List -->
    <div
      ref="subtitlesContainerRef"
      :class="[
        'overflow-y-auto custom-scrollbar',
        compactMode ? 'max-h-[384px] space-y-1' : 'max-h-96 space-y-3'
      ]"
    >
      <!-- 按章节分组显示字幕 -->
      <template v-for="(group, groupIndex) in subtitlesByChapter" :key="groupIndex">
        <!-- 章节分隔符 -->
        <div v-if="group.chapter" class="relative">
          <!-- 亮色分隔线 -->
          <div
            :class="[
              'bg-gradient-to-r from-emerald-500 via-blue-500 to-purple-500 rounded-lg opacity-80 shadow-lg border border-white/20',
              compactMode ? 'h-3' : 'h-5'
            ]"
          ></div>
          <!-- 章节名称 -->
          <div class="absolute inset-0 flex items-center justify-center">
            <span
              :class="[
                'font-semibold text-white shadow-lg border border-slate-600/50 backdrop-blur-sm rounded-full',
                compactMode ? 'bg-slate-800/95 px-2 py-0.5 text-[10px]' : 'bg-slate-800/95 px-4 py-1 text-sm'
              ]"
            >
              {{ group.chapter.title }}
            </span>
          </div>
        </div>

        <!-- 前置内容标识 (在第一个章节之前的字幕) -->
        <div v-else-if="groupIndex === 0 && group.subtitles.length > 0" class="relative">
          <div
            :class="[
              'bg-gradient-to-r from-gray-500 via-slate-600 to-gray-500 rounded-lg opacity-60 shadow-lg border border-white/10',
              compactMode ? 'h-3' : 'h-5'
            ]"
          ></div>
          <div class="absolute inset-0 flex items-center justify-center">
            <span
              :class="[
                'font-medium text-slate-300 shadow-lg border border-slate-600/50 backdrop-blur-sm rounded-full',
                compactMode ? 'bg-slate-800/95 px-2 py-0.5 text-[10px]' : 'bg-slate-800/95 px-4 py-1 text-sm'
              ]"
            >
              开场内容
            </span>
          </div>
        </div>

        <!-- 该章节的字幕列表 -->
        <div
          v-for="(s, i) in group.subtitles"
          :key="`${groupIndex}-${i}`"
          :ref="
            (el) => {
              // 计算全局索引以保持自动滚动功能
              const globalIndex =
                subtitlesByChapter
                  .slice(0, groupIndex)
                  .reduce((acc, g) => acc + g.subtitles.length, 0) + i
              rowRefs[globalIndex] = el as HTMLElement | null
            }
          "
          @click="emit('seek', s.start)"
          :class="[
            'rounded-xl cursor-pointer hover:bg-slate-700/30 transition-all duration-200 border-l-4 backdrop-blur-sm',
            compactMode ? 'p-2' : 'p-4',
            isActive(s)
              ? 'border-blue-500 bg-blue-900/30 shadow-lg'
              : 'border-slate-600/30 hover:border-slate-500/50'
          ]"
        >
          <div :class="['flex items-start', compactMode ? 'gap-2' : 'gap-3']">
            <span
              :class="[
                'font-mono text-blue-400 bg-slate-700/50 rounded-md whitespace-nowrap',
                compactMode ? 'text-[10px] px-1 py-0.5' : 'text-xs px-2 py-1'
              ]"
            >{{ formatTime(s.start) }}</span
            >
            <p
              :class="[
                'flex-1',
                compactMode ? 'text-sm leading-tight text-slate-200' : 'text-slate-200 leading-relaxed'
              ]"
            >{{ s.text }}</p>
          </div>
        </div>
      </template>
    </div>

    <!-- Enhanced Subtitle Dialog -->
    <EnhancedSubtitleDialog
      v-model="showEnhancedSubtitleDialog"
      :video-id-list="[id]"
      :video-name-list="[videoName || '']"
      :current-raw-lang="rawLang"
      @submitted="handleSubtitleDialogSubmitted"
    />
  </div>
</template>
<style lang="css" scoped>
.translation-switch {
  --el-switch-on-color: #3b82f6; /* blue-500 */
  --el-switch-off-color: #475569; /* slate-600 */
}

.blue-checkbox {
  /* border & background that appear after the box is ticked  */
  --el-checkbox-checked-bg-color: #3b82f6; /* ✔ background */
  --el-checkbox-checked-input-border-color: #3b82f6; /* border */
  --el-checkbox-checked-text-color: #3b82f6;
}

/* 自定义滚动条 */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(71, 85, 105, 0.3);
  border-radius: 3px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.5);
  border-radius: 3px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.8);
}
</style>