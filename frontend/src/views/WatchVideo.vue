<!-- 视频播放页面，核心功能 -->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NavBar from '@/components/WatchVideo/NavBar.vue'
import VideoPlayer from '@/components/WatchVideo/VideoPlayer.vue'
import TabbedPanel from '@/components/WatchVideo/TabbedPanel.vue'
import VideoInfo from '@/components/WatchVideo/VideoInfo.vue'
import PlayList from '@/components/WatchVideo/PlayList.vue'
import { blobUrls, generateVTT } from '@/composables/Buildvtt'
import type { VideoInfoData } from '@/types/media.d.ts'
import { getVideoInfo } from '@/composables/GetVideoInfo'
import { hhmmssToSeconds } from '@/composables/TimeFunc'
import { useI18n } from 'vue-i18n'
import { getCSRFToken } from '@/composables/GetCSRFToken'

// 解析URL时间戳参数：支持 #t=90, #t=1m30s, #t=1h30m45s 等格式
function parseTimeString(timeStr: string): number {
  if (!timeStr) return 0

  // 去除空白字符
  timeStr = timeStr.trim()

  // 如果只是纯数字，直接当作秒数处理
  if (/^\d+(\.\d+)?$/.test(timeStr)) {
    return parseFloat(timeStr)
  }

  // 解析时间格式：1h30m45s, 30m45s, 45s 等
  let totalSeconds = 0

  // 提取小时部分
  const hoursMatch = timeStr.match(/(\d+)h/)
  if (hoursMatch) {
    totalSeconds += parseInt(hoursMatch[1]) * 3600
  }

  // 提取分钟部分
  const minutesMatch = timeStr.match(/(\d+)m/)
  if (minutesMatch) {
    totalSeconds += parseInt(minutesMatch[1]) * 60
  }

  // 提取秒数部分
  const secondsMatch = timeStr.match(/(\d+(?:\.\d+)?)s/)
  if (secondsMatch) {
    totalSeconds += parseFloat(secondsMatch[1])
  }

  return totalSeconds
}

// 强类型声明，避免 string | string[] 的 TS 报错
const routeParams = useRoute().params
console.log('Raw route params:', routeParams)

// Get route params and fix basename dot issue
const basenameRaw = (routeParams.basename || routeParams['basename.']) as string
const ext = routeParams.ext as string

const basename = basenameRaw?.replace(/\.$/, '') || ''
const fileName = ref(`${basename}.${ext?.toLowerCase() || ''}`)

// const isVideo = /^(mp4|webm|mkv)$/.test(ext?.toLowerCase() || '')
// Make isAudio reactive to fileName changes (fixes stale media type on route change)
const isAudio = computed(() => {
  const fileExt = fileName.value.split('.').pop()?.toLowerCase() || ''
  return /^(m4a|mp3|wav|aac|flac|alac|ogg|opus)$/.test(fileExt)
})

// i18n functionality
const { t } = useI18n()

const defaultVideoInfo: VideoInfoData = {
  id: -1,
  name: t('unnamedVideo'),
  url: '',
  description: t('noDescription'),
  thumbnailUrl: '',
  videoLength: '00:00',
  lastModified: '',
}

function updateBloburl(blobUrlsAccepted: Array<string | undefined>) {
  blobUrls.value = [...blobUrlsAccepted]
}

// ───────────────── state ─────────────────
const showTranslation = ref(false)
const isVideoFullscreen = ref(false)
const showChapterMarkers = ref(true) // Control chapter marker visibility
import { BACKEND } from '@/composables/ConfigAPI'
const router = useRouter()
const route = useRoute()

// Handle chapter marker toggle from VideoChapters
function handleChapterMarkerToggle(show: boolean) {
  showChapterMarkers.value = show
  console.log(`[WatchVideo] Chapter marker toggle: ${show}`)
}

function navigateToHome() {
  router.push('/')
}
const isStream = route.path.includes('/stream/')
const videoSrc = computed(() => {
  // If route is /stream/, serve HLS
  if (isStream) {
    console.log('Streaming video via HLS:', videoData.value.url)
    const filename = fileName.value.replace(/\.[^/.]+$/, '') // Remove extension
    return `${BACKEND}/media/stream_video/${filename}/index.m3u8`
  }
  const mediaType = isAudio.value ? 'audio' : 'video'
  const src = `${BACKEND}/media/${mediaType}/${fileName.value}`
  console.log('videoSrc updated:', src)
  return src
})
const playerRef = ref<InstanceType<typeof VideoPlayer> | null>(null) // ← ①
const playlistRef = ref<InstanceType<typeof PlayList> | null>(null)

// Autoplay state management
const isAutoPlayEnabled = ref(false)

const duration = ref(0)
const currentTime = ref(0)
const videoProgress = computed(() => (duration.value ? currentTime.value / duration.value : 0))
const pendingResumeTime = ref<number | null>(null)
const PROGRESS_SAVE_INTERVAL_MS = 8000
const PROGRESS_SAVE_MIN_DELTA_SECONDS = 2
const RESUME_END_THRESHOLD_SECONDS = 3
let lastPersistedTime = -1

function handleTimeUpdate(t: number) {
  currentTime.value = t
  // console.log('currentTime', currentTime)
  // console.log(videoProgress.value)
}

function handleSeekFromSubs(t: number) {
  currentTime.value = t // update UI state
  playerRef.value?.seek(t) // ← ② jump the player
}

const videoData = ref<VideoInfoData>(defaultVideoInfo)

// Progress saving
let progressInterval: ReturnType<typeof setInterval> | null = null

const saveProgress = async (options: { force?: boolean } = {}) => {
  if (videoData.value.id <= 0) return

  const current = Number.isFinite(currentTime.value) ? Math.max(0, currentTime.value) : 0
  const nearEnd =
    duration.value > RESUME_END_THRESHOLD_SECONDS &&
    current >= duration.value - RESUME_END_THRESHOLD_SECONDS
  const timeToPersist = nearEnd ? 0 : current

  if (!options.force && Math.abs(timeToPersist - lastPersistedTime) < PROGRESS_SAVE_MIN_DELTA_SECONDS) {
    return
  }

  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/${videoData.value.id}/update_progress`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({ time: timeToPersist }),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`)
    }
    lastPersistedTime = timeToPersist
    console.log('Progress saved:', timeToPersist)
  } catch (err) {
    console.error('Failed to save progress:', err)
  }
}

// Navigation guard: prevents stale loadVideoData from overwriting newer data
// when user switches videos rapidly (A → B, if A finishes after B, discard A)
let navigationId = 0

// Function to load video data.
// Accepts expectedNavId so that if a newer navigation happened while awaiting,
// we skip the state mutation entirely (prevents stale data from overwriting newer data).
async function loadVideoData(filename: string, expectedNavId?: number) {
  try {
    console.log('Loading video data for:', filename)
    const data = await getVideoInfo(filename)

    // Guard: if another navigation started while we were fetching, discard
    if (expectedNavId !== undefined && expectedNavId !== navigationId) {
      console.log('Stale loadVideoData detected, skipping for', filename)
      return
    }

    // Ensure description is never null
    videoData.value = {
      ...data,
      description: data.description || t('noDescription'),
    }

    console.log('Video data loaded:', videoData.value)
    console.log('Video rawLang:', videoData.value.rawLang)

    duration.value = hhmmssToSeconds(videoData.value.videoLength)
    pendingResumeTime.value = null
    lastPersistedTime = Number(data.last_played_time ?? -1)

    // Resume from last played time if available
    if (data.last_played_time && data.last_played_time > 0) {
      const resumeTime = Number(data.last_played_time)
      const isNearEnd =
        duration.value > RESUME_END_THRESHOLD_SECONDS &&
        resumeTime >= duration.value - RESUME_END_THRESHOLD_SECONDS

      if (!isNearEnd) {
        console.log('Resuming from last played time:', resumeTime)
        currentTime.value = resumeTime
        pendingResumeTime.value = resumeTime
      } else {
        currentTime.value = 0
      }
    }

    // Update browser tab title - check if name is not the default
    if (videoData.value.name && videoData.value.name !== t('unnamedVideo')) {
      document.title = `${videoData.value.name} - VidGo`
      console.log('Browser title updated to:', document.title)
    } else {
      console.warn('Video name is empty or default, not updating title')
      // Fallback to filename without extension
      const nameFromFile = filename.replace(/\.[^/.]+$/, '')
      document.title = `${nameFromFile} - VidGo`
    }
  } catch (error) {
    console.error('Failed to load video info:', error)
    // Only set default if this navigation is still current
    if (expectedNavId === undefined || expectedNavId === navigationId) {
      videoData.value = { ...defaultVideoInfo }
      // Fallback to filename without extension
      const nameFromFile = filename.replace(/\.[^/.]+$/, '')
      document.title = `${nameFromFile} - VidGo`
    }
  }
}

// Watch for route params changes to reload video data
watch(
  () => route.params,
  async (newParams, oldParams) => {
    // Simple filename extraction
    const getFileName = (params: any) => {
      if (!params) return ''
      const basename =
        ((params.basename || params['basename.']) as string)?.replace(/\.$/, '') || ''
      const ext = (params.ext as string)?.toLowerCase() || ''
      return `${basename}.${ext}`
    }

    const newFileName = getFileName(newParams)
    const oldFileName = getFileName(oldParams)

    if (newFileName !== oldFileName && newFileName !== '.') {
      console.log('Route changed from', oldFileName, 'to', newFileName)

      // Increment navigation ID to invalidate any in-flight loads
      const currentNavigationId = ++navigationId

      // Update fileName to trigger videoSrc update
      fileName.value = newFileName

      currentTime.value = 0
      duration.value = 0
      pendingResumeTime.value = null
      lastPersistedTime = -1
      videoData.value = { ...defaultVideoInfo }
      await loadVideoData(newFileName, currentNavigationId)

      // Discard result if a newer navigation started while we were loading
      if (currentNavigationId !== navigationId) {
        console.log('Stale navigation detected, discarding result for', newFileName)
        return
      }

      // Handle time jumping after loading new video
      nextTick(() => {
        setTimeout(() => {
          handleTimeJumping()
        }, 500)
      })
    }
  },
  { immediate: false },
)

function handlePlayerReady() {
  const targetTime = pendingResumeTime.value
  if (!targetTime || targetTime <= 0) return

  pendingResumeTime.value = null

  setTimeout(() => {
    playerRef.value?.seek(targetTime)
  }, 50)
}

function handlePlayPauseToggle() {
  if (!playerRef.value) return
}

function handleDescriptionUpdate(newDesc: string) {
  // keep the local state reactive
  videoData.value = { ...videoData.value, description: newDesc }

  // optionally: also update a store or call the backend again here
}

// Handle autoplay settings change
function handleAutoPlaySettingsChanged(enabled: boolean) {
  isAutoPlayEnabled.value = enabled
  console.log(`[WatchVideo] Autoplay settings changed: ${enabled ? 'enabled' : 'disabled'}`)
}

// Handle fullscreen change for iOS compatibility
function handleFullscreenChange(isFullscreen: boolean) {
  isVideoFullscreen.value = isFullscreen
  console.log(`[WatchVideo] Fullscreen state changed: ${isFullscreen}`)
}

// Handle autoplay next video request
function handleAutoPlayNext() {
  if (!isAutoPlayEnabled.value || !playlistRef.value) {
    console.log('[WatchVideo] Autoplay not enabled or playlist not available')
    return
  }

  console.log('[WatchVideo] Attempting to play next video in collection')

  // Get next video from playlist
  const nextVideo = playlistRef.value.getNextVideo()

  if (nextVideo) {
    console.log(`[WatchVideo] Playing next video: ${nextVideo.name}`)
    // Extract filename from video.url
    const filename = nextVideo.url.split('/').pop() || nextVideo.url
    // Navigate to next video
    router.push(`/watch/${encodeURIComponent(filename)}`)
  } else {
    console.log('[WatchVideo] No next video available, reached end of collection')
  }
}

// Function to handle URL fragment time jumping
function handleTimeFragment() {
  const hash = window.location.hash
  if (hash.startsWith('#t=')) {
    const timeStr = hash.substring(3) // Remove '#t='
    const jumpToSeconds = parseTimeString(timeStr)

    if (jumpToSeconds > 0) {
      console.log(`[WatchVideo] Jumping to time: ${jumpToSeconds}s from URL fragment`)

      // Set current time and seek to the position
      currentTime.value = jumpToSeconds

      // Use setTimeout to ensure the video player is ready
      setTimeout(() => {
        if (playerRef.value) {
          playerRef.value.seek(jumpToSeconds)
          console.log(`[WatchVideo] Successfully jumped to ${jumpToSeconds}s`)
        }
      }, 100)
    }
  }
}

// Function to check for query parameter time and handle it
function handleQueryTimeParameter() {
  const urlParams = new URLSearchParams(window.location.search)
  const timeParam = urlParams.get('t')

  if (timeParam) {
    const jumpToSeconds = parseTimeString(timeParam)

    if (jumpToSeconds > 0) {
      console.log(`[WatchVideo] Jumping to time: ${jumpToSeconds}s from query parameter`)

      // Set current time and seek to the position
      currentTime.value = jumpToSeconds

      // Use setTimeout to ensure the video player is ready
      setTimeout(() => {
        if (playerRef.value) {
          playerRef.value.seek(jumpToSeconds)
          console.log(`[WatchVideo] Successfully jumped to ${jumpToSeconds}s`)
        }
      }, 100)

      // Optionally update URL fragment to maintain consistency
      window.history.replaceState(null, '', window.location.pathname + `#t=${jumpToSeconds}`)
    }
  }
}

// Combined function to handle both fragment and query parameter time jumping
function handleTimeJumping() {
  // Priority: URL fragment takes precedence over query parameter
  const hash = window.location.hash
  if (hash.startsWith('#t=')) {
    handleTimeFragment()
  } else {
    handleQueryTimeParameter()
  }
}

// Function to update URL with current time (for creating shareable timestamps)
function updateUrlWithCurrentTime(seconds: number) {
  const newHash = `#t=${Math.round(seconds)}`
  if (window.location.hash !== newHash) {
    // Update URL without triggering navigation
    window.history.replaceState(
      null,
      '',
      window.location.pathname + window.location.search + newHash,
    )
  }
}

onMounted(async () => {
  console.log('Route params:', routeParams)
  console.log('basename:', basename)
  console.log('ext:', ext)
  console.log('fileName:', fileName)
  console.log('Current path:', route.path)
  console.log('isStream (from props):', isStream) // ✅ ADD: Debug log

  await loadVideoData(fileName.value)

  // Handle initial URL time jumping (both fragment and query parameter)
  setTimeout(() => {
    handleTimeJumping()
  }, 500) // Wait for video player to be fully initialized

  // Listen for hash changes for shareable timestamps
  window.addEventListener('hashchange', handleTimeFragment)

  // Start progress saving timer
  progressInterval = setInterval(() => {
    void saveProgress()
  }, PROGRESS_SAVE_INTERVAL_MS)
})

// Cleanup event listeners when component unmounts
onUnmounted(() => {
  window.removeEventListener('hashchange', handleTimeFragment)
  
  if (progressInterval) {
    clearInterval(progressInterval)
    progressInterval = null
  }
  // Save progress one last time
  void saveProgress({ force: true })
})

// ✅ FIX: Enhanced HLS.js mounting with detailed debugging
onMounted(() => {
  if (isStream) {
    console.log('[HLS] Initializing HLS for streaming')
    import('hls.js')
      .then(({ default: Hls }) => {
        const videoEl: HTMLVideoElement | null = document.querySelector('video')
        if (videoEl && Hls.isSupported()) {
          const hls = new Hls({
            // === 性能优化配置 ===
            debug: false, // 生产环境关闭debug
            enableWorker: true, // 启用Web Worker提升性能
            lowLatencyMode: false, // 点播模式，优化缓冲

            // === 缓冲优化 ===
            maxBufferLength: 60, // 最大缓冲60秒
            maxBufferSize: 60 * 1000 * 1000, // 最大缓冲60MB
            maxBufferHole: 0.3, // 允许0.3秒缓冲空洞

            // === 片段加载优化 ===
            maxLoadingTimeout: 10000, // 减少超时时间
            fragLoadingTimeOut: 8000, // 片段加载超时
            fragLoadingMaxRetry: 3, // 减少重试次数，快速失败
            fragLoadingRetryDelay: 500, // 重试间隔500ms
            manifestLoadingTimeOut: 5000, // manifest超时
            manifestLoadingMaxRetry: 2,

            // === 质量选择优化 ===
            startLevel: -1, // 自动选择起始质量
            abrEwmaDefaultEstimate: 1000000, // 默认带宽估算1Mbps
            abrBandWidthFactor: 0.95, // 保守的带宽使用
            abrBandWidthUpFactor: 0.7, // 向上切换更保守
            abrMaxWithRealBitrate: true, // 使用真实比特率

            // === 网络优化 ===
            xhrSetup: function (xhr: any, url: any) {
              // 设置缓存策略
              if (url.endsWith('.ts')) {
                xhr.setRequestHeader('Cache-Control', 'public, max-age=3600')
              }
              // 设置超时
              xhr.timeout = 8000
            },

            // === 其他优化 ===
            capLevelToPlayerSize: true, // 根据播放器大小限制质量
            testBandwidth: false, // 跳过带宽测试，减少启动时间
            progressive: false, // 关闭渐进式加载
          })

          // Enhanced event logging
          hls.on(Hls.Events.MANIFEST_LOADED, (event: any, data: any) => {
            console.log('[HLS] Manifest loaded:', data)
          })

          hls.on(Hls.Events.LEVEL_LOADED, (event: any, data: any) => {
            console.log('[HLS] Level loaded:', data)
          })

          hls.on(Hls.Events.FRAG_LOADING, (event: any, data: any) => {
            console.log('[HLS] Fragment loading:', data.frag.url)
          })

          hls.on(Hls.Events.FRAG_LOADED, (event: any, data: any) => {
            console.log('[HLS] Fragment loaded successfully:', data.frag.url)
          })

          hls.on(Hls.Events.FRAG_LOAD_ERROR, (event: any, data: any) => {
            console.error('[HLS] Fragment load error:', data)
            console.error('[HLS] Failed URL:', data.frag?.url)
            console.error('[HLS] HTTP Status:', data.response?.code)
          })

          hls.on(Hls.Events.ERROR, (event: any, data: any) => {
            console.error('[HLS] General Error:', event, data)
            console.error('[HLS] Error Type:', data.type)
            console.error('[HLS] Error Details:', data.details)
            console.error('[HLS] Error Response:', data.response)

            if (data.fatal) {
              switch (data.type) {
                case Hls.ErrorTypes.NETWORK_ERROR:
                  console.log('[HLS] Fatal network error, trying to recover...')
                  hls.startLoad()
                  break
                case Hls.ErrorTypes.MEDIA_ERROR:
                  console.log('[HLS] Fatal media error, trying to recover...')
                  hls.recoverMediaError()
                  break
                default:
                  console.log('[HLS] Fatal error, destroying HLS instance')
                  hls.destroy()
                  break
              }
            }
          })

          console.log('[HLS] Loading source:', videoSrc.value)
          hls.loadSource(videoSrc.value)
          hls.attachMedia(videoEl)

          console.log('[HLS] HLS instance created and attached')
        } else {
          console.warn('[HLS] HLS.js not supported')
        }
      })
      .catch((error) => {
        console.error('[HLS] Failed to load HLS.js:', error)
      })
  } else {
    console.log('[HLS] Normal video playback mode')
  }
})
</script>

<template>
  <!-- 深色主题背景容器 -->
  <div class="min-h-screen bg-gradient-to-br from-gray-900 via-slate-800 to-blue-900">
    <!-- 导航栏组件，含用户信息与设置按钮 -->
    <NavBar
      v-if="!isVideoFullscreen"
      :showTranslation="showTranslation"
      :progress="videoProgress"
      :currentTime="currentTime"
      :videoLength="videoData.videoLength"
      :title="videoData.name"
      :filename="fileName"
      @toggle-translation="showTranslation = !showTranslation"
      @open-settings="navigateToHome"
    />

    <!-- 主要内容区域 -->
    <div class="p-6">
      <div :class="isVideoFullscreen ? 'grid grid-cols-1' : 'grid lg:grid-cols-3 gap-6'">
        <!-- 左侧视频播放区域 -->
        <div :class="isVideoFullscreen ? 'col-span-1 space-y-4' : 'lg:col-span-2 space-y-4'">
          <!-- 视频播放器卡片容器 -->
          <div
            class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl p-4 border border-slate-600/50 shadow-2xl"
          >
            <div class="aspect-video w-full rounded-xl overflow-hidden">
              <VideoPlayer
                ref="playerRef"
                :src="videoSrc"
                :blobUrls="blobUrls"
                :videoId="videoData.id"
                :rawLang="videoData.rawLang"
                :videoName="videoData.name"
                :showChapterMarkers="showChapterMarkers"
                @time-update="handleTimeUpdate"
                @autoplay-next="handleAutoPlayNext"
                @autoplay-settings-changed="handleAutoPlaySettingsChanged"
                @fullscreen-change="handleFullscreenChange"
                @ready="handlePlayerReady"
                class="w-full h-full"
              />
            </div>
          </div>

          <!-- 视频信息卡片，带选项卡 -->
          <div
            class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl border border-slate-600/50 shadow-2xl"
            :class="{ 'fullscreen-hidden': isVideoFullscreen }"
          >
            <Suspense>
              <template #default>
                <VideoInfo
                  :key="`info-${fileName}-${videoData.id}`"
                  :filename="fileName"
                  :title="videoData.name"
                  :description="videoData.description"
                  @update:description="handleDescriptionUpdate"
                  :id="videoData.id"
                />
              </template>
              <template #fallback>
                <div class="text-slate-400 p-6">{{ t('loadingVideoInfo') }}</div>
              </template>
            </Suspense>
          </div>
        </div>

        <!-- 右侧侧边栏 -->
        <div v-show="!isVideoFullscreen" class="space-y-4" :class="{ 'fullscreen-hidden': isVideoFullscreen }">
          <!-- 选项卡面板卡片 -->
          <div
            class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl border border-slate-600/50 shadow-2xl"
          >
            <TabbedPanel
              v-if="videoData.id !== -1"
              :key="`tabbed-${fileName}-${videoData.id}`"
              :currentTime="currentTime"
              :id="videoData.id"
              :rawLang="videoData.rawLang"
              :videoName="videoData.name"
              :showChapterMarkers="showChapterMarkers"
              @update-bloburls="updateBloburl"
              @seek="handleSeekFromSubs"
              @toggle-chapter-markers="handleChapterMarkerToggle"
            />
            <div v-else class="text-slate-400 text-center py-8">{{ t('loadingSubtitles') }}</div>
          </div>

          <!-- 播放列表卡片 -->
          <div
            class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl border border-slate-600/50 shadow-2xl"
          >
            <PlayList
              ref="playlistRef"
              :current-video-id="videoData.id"
              :current-video-filename="fileName"
            />
          </div>
        </div>
      </div>
    </div>

    
  </div>
</template>

<style scoped>
/* 全屏处理 - 隐藏其他组件 */
.fullscreen-hidden {
  display: none !important;
  visibility: hidden !important;
}

/* 修复 Video.js 全屏模式下字幕显示层级 */
:deep(.video-js.vjs-fullscreen) {
  z-index: 2147483647 !important;
}

:deep(.vjs-fullscreen .vjs-text-track-display) {
  z-index: 1000 !important; /* 字幕位于视频之上 */
}

:deep(.vjs-fullscreen .vjs-control-bar) {
  z-index: 1001 !important; /* 控件位于字幕之上 */
}

:deep(.vjs-fullscreen .vjs-menu) {
  z-index: 1002 !important; /* 菜单位于控件之上 */
}

:deep(.vjs-fullscreen .vjs-modal-dialog) {
  z-index: 1003 !important; /* 弹窗位于最上层 */
}

/* 确保全屏模式下快捷键提示显示最上层 */
.fixed.z-50 {
  z-index: 1004 !important;
}
</style>
