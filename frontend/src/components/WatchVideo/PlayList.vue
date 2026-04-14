<script lang="ts" setup>
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { Video } from '@/types/media'
import { getSimilarVideos, type SimilarVideoResponse } from '@/composables/SimilarVideosAPI'
import { BACKEND } from '@/composables/ConfigAPI'

const props = defineProps<{
  currentVideoId: number
  currentVideoFilename?: string
}>()

const { t } = useI18n()

const router = useRouter()

const similarVideos = ref<SimilarVideoResponse[]>([])
const isLoading = ref(false)
const showThumbnails = ref(true)

const loadSimilarVideos = async () => {
  if (props.currentVideoId === -1) {
    similarVideos.value = []
    return
  }

  isLoading.value = true
  try {
    similarVideos.value = await getSimilarVideos(props.currentVideoId)
  } catch (error) {
    console.error('Failed to load similar videos:', error)
    similarVideos.value = []
  } finally {
    isLoading.value = false
  }
}

const switchVideo = (video: SimilarVideoResponse): void => {
  if (video.id === props.currentVideoId) {
    return
  }

  const filename = video.url.split('/').pop() || video.url
  router.push(`/watch/${encodeURIComponent(filename)}`)
}

const getThumbnailUrl = (video: SimilarVideoResponse): string => {
  if (!video.thumbnail_url) {
    return ''
  }

  if (video.thumbnail_url.startsWith('http')) {
    return video.thumbnail_url
  }

  return `${BACKEND}/media/thumbnail/${encodeURIComponent(video.thumbnail_url)}`
}

const formatDuration = (length: string): string => {
  if (length.includes(':')) {
    return length
  }
  const totalSeconds = parseInt(length, 10)
  if (isNaN(totalSeconds)) {
    return length
  }

  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
  } else {
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }
}

const isCurrentVideo = (video: SimilarVideoResponse): boolean => {
  if (props.currentVideoFilename) {
    const videoFilename = video.url.split('/').pop() || video.url
    return videoFilename === props.currentVideoFilename
  }

  if (props.currentVideoId && video.id && props.currentVideoId !== -1) {
    return video.id === props.currentVideoId
  }

  return false
}

const getNextVideo = (): SimilarVideoResponse | null => {
  const currentIndex = similarVideos.value.findIndex(
    (v) => v.id === props.currentVideoId
  )
  if (currentIndex === -1 || currentIndex === similarVideos.value.length - 1) {
    return null
  }
  return similarVideos.value[currentIndex + 1]
}

defineExpose({
  getNextVideo,
})

onMounted(() => {
  try {
    const saved = localStorage.getItem('vidgo_playlist_show_thumbnails')
    if (saved !== null) {
      showThumbnails.value = saved === 'true'
    }
  } catch (error) {
    console.error('Failed to restore playlist thumbnail preference:', error)
  }
  loadSimilarVideos()
})

watch(() => props.currentVideoId, () => {
  loadSimilarVideos()
})

watch(showThumbnails, (nextValue) => {
  try {
    localStorage.setItem('vidgo_playlist_show_thumbnails', String(nextValue))
  } catch (error) {
    console.error('Failed to persist playlist thumbnail preference:', error)
  }
})
</script>
<template>
  <div class="bg-slate-800/30 rounded-2xl p-6 backdrop-blur-lg border border-slate-600/30">
    <div class="mb-6 flex items-center justify-between gap-4">
      <h2 class="text-xl font-semibold text-white">
        {{ t('collectionPlaylist') }}
      </h2>

      <label class="flex items-center gap-2 text-sm text-slate-300">
        <span>展示缩略图</span>
        <el-switch v-model="showThumbnails" inline-prompt class="playlist-thumbnail-toggle" />
      </label>
    </div>

    <div v-if="isLoading" class="text-center py-8">
      <div class="text-slate-400">{{ t('loadingVideoInfo') }}</div>
    </div>

    <div v-else-if="similarVideos.length === 0" class="text-center py-8">
      <div class="text-slate-400 mb-2">
        <svg
          class="w-12 h-12 mx-auto mb-3 opacity-50"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
          ></path>
        </svg>
        <p class="text-sm">没有相同标签和分类的视频</p>
      </div>
    </div>

    <div v-else class="space-y-3 max-h-[600px] overflow-y-auto custom-scrollbar">
      <div
        v-for="video in similarVideos"
        :key="video.id"
        @click="switchVideo(video)"
        :class="[
          'flex items-center rounded-xl cursor-pointer transition-all duration-200',
          showThumbnails ? 'gap-3 p-3' : 'gap-2.5 px-3 py-2.5',
          'hover:bg-slate-700/50',
          isCurrentVideo(video)
            ? 'bg-blue-600/30 ring-2 ring-blue-500/50'
            : 'bg-slate-700/20',
        ]"
      >
        <div
          v-if="showThumbnails"
          class="relative h-20 w-32 flex-shrink-0 overflow-hidden rounded-lg bg-slate-800"
        >
          <img
            v-if="getThumbnailUrl(video)"
            :src="getThumbnailUrl(video)"
            :alt="video.name"
            class="w-full h-full object-cover"
          />
          <div v-else class="w-full h-full flex items-center justify-center text-slate-600">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
          </div>
          <div
            v-if="video.video_length"
            class="absolute bottom-1 right-1 bg-black/80 text-white text-xs px-1.5 py-0.5 rounded"
          >
            {{ formatDuration(video.video_length) }}
          </div>
        </div>

        <div class="flex-1 min-w-0">
          <div
            :class="[
              'truncate font-medium',
              showThumbnails ? 'text-sm' : 'text-[0.95rem]',
              isCurrentVideo(video) ? 'text-blue-400' : 'text-white',
            ]"
          >
            {{ video.name }}
          </div>
          <div class="mt-1 text-slate-400" :class="showThumbnails ? 'text-xs' : 'text-[0.8rem]'">
            {{ video.video_length || '时长未知' }}
          </div>
        </div>

        <div v-if="isCurrentVideo(video)" class="flex-shrink-0">
          <div
            class="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center"
          >
            <svg class="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path
                fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.playlist-thumbnail-toggle {
  --el-switch-on-color: #0891b2;
  --el-switch-off-color: #334155;
}

/* Custom scrollbar */
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
