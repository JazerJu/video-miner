<!-- 字幕编辑器，核心功能 -->
<template>
  <!-- 深色主题背景容器,min-h-screen:这个元素的最小高度等于整个视口的高度。 -->
  <div class="min-h-screen bg-[#1B316A]">
    <!-- 头部导航栏 -->
    <NavBar
      :showTranslation="showTranslation"
      :progress="videoProgress"
      :currentTime="currentTime"
      :videoLength="videoData.videoLength"
      :title="videoData.name"
      :filename="fileName"
      @toggle-translation="showTranslation = !showTranslation"
      @go-back="console.log('come back')"
      @open-settings="navigateToHome"
    />
    <div class="h-[calc(100vh+70px)] flex gap-6 p-6 min-w-0">
      <!-- 左侧视频和波形区域 -->
      <div class="flex-[2] flex flex-col min-h-0 gap-6 min-w-0">
        <!-- 视频播放器 -->
        <div
          class="flex-[2] flex flex-col min-h-0 bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl p-4 border border-slate-600/50 shadow-2xl min-w-0"
        >
          <!-- 使用填充容器替代 aspect-video，以便可伸缩 -->
          <div class="relative w-full h-full overflow-hidden">
            <VideoPlayer
              ref="playerRef"
              :src="videoSrc"
              :blobUrls="blobUrls"
              :videoId="videoData.id"
              @time-update="handleTimeUpdate"
              class="absolute inset-0 w-full h-full"
            />
          </div>
        </div>

        <!-- 波形查看器 -->
        <div
          ref="waveformContainerRef"
          class="flex-[1] p-4 border border-slate-600/50 bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl shadow-2xl min-w-0"
        >
          <WaveformViewer
            v-if="waveformReady"
            :subtitles="subtitles"
            :video-id="videoData.id"
            :video-url="videoSrc"
            :blobUrls="blobUrls"
            :current-time="currentTime"
            :duration="duration"
            :show-regions="showRegions"
            :height="waveformHeight"
            @seek="handleSeekFromWaveform"
            @update:show-regions="showRegions = $event"
            @subtitle-updated="handleSubtitleUpdated"
          />
        </div>
      </div>

      <!-- 右侧字幕编辑器 - 占满右侧 -->
      <div class="flex-[1] h-full min-h-0">
        <div
          class="bg-gradient-to-r from-slate-800/90 to-slate-700/90 backdrop-blur-lg rounded-2xl border border-slate-600/50 shadow-2xl h-full min-h-0 min-w-0"
        >
          <SubtitleEditor
            ref="subtitleEditorRef"
            :current-time="currentTime"
            :id="videoData.id"
            :rawLang="videoData.rawLang"
            :videoName="videoData.name"
            :duration="duration"
            @seek-time="handleSeekFromSubs"
            @update-bloburls="updateBloburl"
            @subs-loaded="subsLoad"
            class="w-full h-full"
          />
        </div>
      </div>
    </div>
    
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import type { Subtitle } from '@/types/subtitle'
import { ElMessage } from 'element-plus'
import { blobUrls } from '@/composables/Buildvtt'
import type { VideoInfoData } from '@/types/media.d.ts'
import { getVideoInfo } from '@/composables/GetVideoInfo'
import { hhmmssToSeconds } from '@/composables/TimeFunc'
import { useRoute, useRouter } from 'vue-router'

import NavBar from '@/components/WatchVideo/NavBar.vue'
import VideoPlayer from '@/components/WatchVideo/VideoPlayer.vue'
import SubtitleEditor from '@/components/Editor/SubtitleEditor.vue'
import WaveformViewer from '@/components/Editor/WaveformViewer.vue'

const subtitles = ref<Subtitle[]>([]) // 存真正的字幕数组
const waveformContainerRef = ref<HTMLDivElement>()
const waveformHeight = ref(200) // 默认高度
let waveformResizeObserver: ResizeObserver | null = null

function subsLoad(raw: Subtitle[]) {
  // 注意 raw 是数组
  console.log('subtitles accepted by editor:', raw)
  subtitles.value = raw
}

const defaultVideoInfo: VideoInfoData = {
  id: -1,
  name: '（未命名视频）',
  url: '',
  description: '暂无描述',
  thumbnailUrl: '',
  videoLength: '00:00',
  lastModified: '',
}

const playerRef = ref<InstanceType<typeof VideoPlayer> | null>(null) // ← ①
const subtitleEditorRef = ref<InstanceType<typeof SubtitleEditor> | null>(null)

// 路由配置
const route = useRoute()
const router = useRouter()

function navigateToHome() {
  router.push('/')
}

// 获取并处理路由参数（参考 WatchVideo.vue）
const routeParams = route.params
const basenameRaw = (routeParams.basename || routeParams['basename.']) as string
const ext = routeParams.ext as string

// 去除末尾点并生成文件名
const basename = basenameRaw?.replace(/\.$/, '') || ''
const fileName = ref(`${basename}.${ext?.toLowerCase() || ''}`)

const isAudio = /^(m4a|mp3|wav)$/.test(ext?.toLowerCase() || '')

// ───────────────── 状态 ─────────────────
const showTranslation = ref(false)

function updateBloburl(blobUrlsAccepted: Array<string | undefined>) {
  blobUrls.value = [...blobUrlsAccepted]
  console.log(blobUrls)
}

function handleSeekFromWaveform(t: number) {
  // 点击对应位置的字幕,视频自动跳转到对应时间.
  currentTime.value = t
  console.log(currentTime.value)
  playerRef.value?.seek(t) // ← ② 跳转播放器至对应时间
}

const videoProgress = computed(() => (duration.value ? currentTime.value / duration.value : 0))
// 随时间变化改变"current-Time"等参数，从而影响Subtitle Editor 和wave surfer region的高亮。
function handleTimeUpdate(t: number) {
  currentTime.value = t
  console.log('currentTime', currentTime)
  console.log(videoProgress.value)
}
// 不再需要通过 props 获取参数，直接使用路由

const videoData = ref<VideoInfoData>(defaultVideoInfo)

const showRegions = ref(true) // 控制波形区域可见性
const videoId = ref(-1)

// 字幕样式现在通过 useSubtitleStyle 从首页设置中加载

const currentTime = ref(0)
function handleSeekFromSubs(t: number) {
  // 点击对应位置的字幕,视频自动跳转到对应时间.
  currentTime.value = t
  playerRef.value?.seek(t) // ← ② 跳转播放器至对应时间
}

function handleSubtitleUpdated(index: number, newStart: number, newEnd: number) {
// 拖动波形区域时更新字幕数据
  if (subtitles.value[index]) {
    subtitles.value[index].start = newStart
    subtitles.value[index].end = newEnd

    // 强制触发响应式更新
    subtitles.value = [...subtitles.value]

    // 同时更新字幕编辑器内部数据
    if (subtitleEditorRef.value && 'updateSubtitleTiming' in subtitleEditorRef.value) {
      ;(subtitleEditorRef.value as any).updateSubtitleTiming(index, newStart, newEnd)
    }

    console.log(`Subtitle ${index} updated: ${newStart}s - ${newEnd}s`)
  }
}

const duration = ref(0)
const progressPercentage = computed(() => {
  if (duration.value <= 0) return 0
  return (currentTime.value / duration.value) * 100
})

import { BACKEND } from '@/composables/ConfigAPI'
import { useSubtitleStyle } from '@/composables/SubtitleStyle'

// 加载字幕样式设置
const { subtitleSettings, foreignSubtitleSettings, loadSubtitleSettings } = useSubtitleStyle()
const videoSrc = computed(() => {
  const mediaType = isAudio ? 'audio' : 'video'
  const src = `${BACKEND}/media/${mediaType}/${fileName.value}`
  console.log('videoSrc updated:', src)
  return src
})

// 加载视频数据函数（参考 WatchVideo.vue）
async function loadVideoData(filename: string) {
  try {
    console.log('Loading video data for:', filename)
    const data = await getVideoInfo(filename)

    // 确保 description 不为空
    videoData.value = {
      ...data,
      description: data.description || '暂无描述',
    }

    // console.log('Video data loaded:', videoData.value)
    // console.log('Video rawLang:', videoData.value.rawLang)

    duration.value = hhmmssToSeconds(videoData.value.videoLength)
    videoId.value = videoData.value.id

    // 更新浏览器标签标题，若名称不是默认
    if (videoData.value.name && videoData.value.name !== '（未命名视频）') {
      document.title = `${videoData.value.name} - VidGo 字幕编辑器`
      console.log('Browser title updated to:', document.title)
    } else {
      console.warn('Video name is empty or default, not updating title')
      // 回退到无扩展名的文件名
      const nameFromFile = filename.replace(/\.[^/.]+$/, '')
      document.title = `${nameFromFile} - VidGo 字幕编辑器`
    }
  } catch (error) {
    console.error('Failed to load video info:', error)
    // 设置默认视频数据
    videoData.value = { ...defaultVideoInfo }
    // 回退到无扩展名的文件名
    const nameFromFile = filename.replace(/\.[^/.]+$/, '')
    document.title = `${nameFromFile} - VidGo 字幕编辑器`
    ElMessage.error('加载视频信息失败')
  }
}

// 监听路由参数变化以重新加载视频数据
const waveformReady = ref(false)
onMounted(async () => {
  // console.log('Route params:', routeParams)
  // console.log('basename:', basename)
  // console.log('ext:', ext)
  // console.log('fileName:', fileName)
  // console.log('Current path:', route.path)
  await loadVideoData(fileName.value)
  waveformReady.value = true // 再让子组件挂载
  
  // 加载首页保存的字幕样式设置
  await loadSubtitleSettings()
  console.log('[SubtitleEditorView] Loaded subtitle settings:', {
    raw: subtitleSettings.value,
    foreign: foreignSubtitleSettings.value
  })

  // 设置波形容器的 ResizeObserver
  if (waveformContainerRef.value) {
    waveformResizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { height } = entry.contentRect
        // 计算波形高度，并考虑内边距调整
        const newHeight = Math.max(150, height - 80) // 更保守的内边距调整，以适应头部和边距
        // 仅在变化显著时更新，防止循环反馈
        if (Math.abs(newHeight - waveformHeight.value) > 10) {
          console.log('Updating waveform height from', waveformHeight.value, 'to', newHeight)
          waveformHeight.value = newHeight
        }
      }
    })
    waveformResizeObserver.observe(waveformContainerRef.value)
  }
})

onBeforeUnmount(() => {
  if (waveformResizeObserver) {
    waveformResizeObserver.disconnect()
    waveformResizeObserver = null
  }
})
</script>
