<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { ElTooltip } from 'element-plus'
import { ElMessage } from '@/composables/useNotification'
import { useRouter, useRoute } from 'vue-router'
import { FilePen, Video, Settings, Sun, Moon } from 'lucide-vue-next'
import { useUser } from '@/composables/useUser'
import { useTheme } from '@/composables/useTheme'

const { theme, toggleTheme } = useTheme()

const router = useRouter()
const route = useRoute()

const props = defineProps<{
  showTranslation: boolean
  progress: number
  currentTime: number // Current playback time in seconds
  videoLength: string // Video duration in format '00:08:04'
  title?: string // Video title for display
  filename?: string // Filename for route navigation
}>()

// Check if title is truncated
const titleRef = ref<HTMLElement>()
const isTextTruncated = ref(false)

const checkTruncation = async () => {
  await nextTick()
  if (titleRef.value) {
    isTextTruncated.value = titleRef.value.scrollWidth > titleRef.value.clientWidth
  }
}

watch(() => props.title, checkTruncation, { immediate: true })

// User management
const { username, userInitial, isLoggedIn, checkUserStatus } = useUser()

const emit = defineEmits<{
  (e: 'update:showTranslation', value: boolean): void
  (e: 'toggle-translation'): void
  (e: 'show-progress'): void
  (e: 'open-settings'): void
}>()

const showTranslationProxy = computed({
  get: () => props.showTranslation,
  set: (v) => {
    emit('update:showTranslation', v)
    emit('toggle-translation') // Toggle between translation and raw subtitle display
  },
})

const showProgress = ref(false)
watch(
  () => props.progress,
  () => {
    console.log(props.progress)
  },
)
function formatTime(sec: number): string {
  sec = Math.floor(sec) // 只保留整数
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':')
}

function mouseEnter() {
  showProgress.value = true
}

// function mouseLeave() {
//   showProgress.value = false
//   ElMessage.info({
//     message: `${formatTime(props.currentTime)} / ${props.videoLength}`,
//     duration: 1500, // 1.5 秒后自动关闭
//     offset: 60, // （可选）距离顶部 60 px
//     grouping: true, // （可选）相同内容只出现一次
//   })
// }
const progressStyle = computed(() => ({
  width: `${props.progress * 100}%`,
}))

const goHome = () => {
  router.push('/')
}

// 判断当前是否在编辑器视图
const isInEditor = computed(() => route.name === 'subtitle-editor')

// 切换视图功能
const toggleView = () => {
  if (!props.filename) {
    console.warn('No filename provided for view switching')
    return
  }

  if (isInEditor.value) {
    // 从编辑器切换到观看视频
    router.push(`/watch/${props.filename}`)
  } else {
    // 从观看视频切换到编辑器
    router.push(`/editor/${props.filename}`)
  }
}

// Check user status on mount
onMounted(() => {
  checkUserStatus()
})
</script>
<template>
  <!-- 主题顶部导航栏 -->
  <div
    class="nav-bar bg-white/90 dark:bg-slate-800/95 backdrop-blur-lg border-b border-slate-200 dark:border-white/10 px-6 py-4 relative shadow-lg shadow-slate-200/70 dark:shadow-black/20 transition-colors duration-300"
    @mouseenter="mouseEnter"
  >
    <div class="flex justify-between items-center">
      <!-- 左侧HOME按钮和标题 -->
      <div class="flex items-center space-x-6 basis-2/3 min-w-0">
        <button
          @click="goHome"
          class="flex items-center justify-center w-10 h-10 rounded-full bg-white/80 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 transition-colors flex-shrink-0 border border-slate-200 dark:border-white/10"
        >
          <svg class="w-5 h-5 text-slate-600 dark:text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
            ></path>
          </svg>
        </button>

        <!-- 视频标题 -->
        <div v-if="title" class="max-w-[60%] overflow-hidden">
          <el-tooltip :content="title" placement="bottom" :disabled="!isTextTruncated">
            <h1
              ref="titleRef"
              class="text-xl font-semibold text-slate-900 dark:text-white truncate"
              @mouseenter="checkTruncation"
            >
              {{ title }}
            </h1>
          </el-tooltip>
        </div>
      </div>

      <!-- 右侧用户信息和按钮 -->
      <div class="flex items-center space-x-4 basis-1/3 justify-end">
        <!-- 用户名 -->
        <div class="flex items-center space-x-3">
          <div
            class="w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center"
          >
            <span class="text-white font-semibold text-sm">{{ userInitial }}</span>
          </div>
          <span class="text-slate-700 dark:text-slate-300 font-medium">{{ username }}</span>
        </div>

        <!-- 视图切换按钮 -->
        <el-tooltip :content="isInEditor ? 'Video Watch' : 'Edit'" placement="bottom">
          <button
            @click="toggleView"
            class="flex items-center justify-center px-4 py-2 rounded-lg bg-white/80 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 transition-colors border border-slate-200 dark:border-white/10"
          >
            <Video v-if="isInEditor" class="w-4 h-4 text-slate-600 dark:text-slate-300 mr-2" />
            <FilePen v-else class="w-4 h-4 text-slate-600 dark:text-slate-300 mr-2" />
            <span class="text-slate-700 dark:text-slate-300 text-sm font-medium">
              {{ isInEditor ? 'Video Watch' : 'Edit' }}
            </span>
          </button>
        </el-tooltip>

        <!-- 主题切换按钮 -->
        <el-tooltip :content="theme === 'dark' ? '切换亮色模式' : '切换暗色模式'" placement="bottom">
          <button
            @click="toggleTheme"
            class="flex items-center justify-center w-10 h-10 rounded-full bg-white/80 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 transition-colors border border-slate-200 dark:border-white/10"
          >
            <Sun v-if="theme === 'dark'" class="w-5 h-5 text-slate-300" />
            <Moon v-else class="w-5 h-5 text-slate-600" />
          </button>
        </el-tooltip>

        <!-- 设置按钮 -->
        <el-tooltip content="设置" placement="bottom">
          <button
            @click="emit('open-settings')"
            class="flex items-center justify-center w-10 h-10 rounded-full bg-white/80 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 transition-colors border border-slate-200 dark:border-white/10"
          >
            <Settings class="w-5 h-5 text-slate-600 dark:text-slate-300" />
          </button>
        </el-tooltip>
      </div>
    </div>

    <!-- progress bar (shows only on hover) -->
    <transition name="fade">
      <div v-show="showProgress" class="absolute bottom-0 left-0 w-full h-1 bg-slate-200/80 dark:bg-slate-700/50">
        <div class="h-full bg-blue-500 transition-[width] duration-300" :style="progressStyle" />
      </div>
    </transition>
  </div>
</template>
