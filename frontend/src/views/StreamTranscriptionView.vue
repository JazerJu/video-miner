<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  ArrowBigDown,
  ChevronRight,
  Clock3,
  Link2,
  Radio,
  Settings2,
  Waves,
  X,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import VideoPlayer from '@/components/WatchVideo/VideoPlayer.vue'
import {
  cancelTranscription,
  connectTranscriptionSSE,
  getRelayedUrl,
  resolveStream,
  startTranscription,
  type ResolvedStream,
  type TranscriptionSegment,
} from '@/composables/StreamTranscriptionAPI'
import { loadSettings } from '@/composables/ConfigAPI'

const { t } = useI18n()

const streamUrl = ref('')
const resolving = ref(false)
const startingTranscription = ref(false)
const resolveError = ref('')
const transcriptionError = ref('')
const resolvedStream = ref<ResolvedStream | null>(null)
const taskId = ref('')
const transcriptionStatus = ref<'idle' | 'running' | 'completed' | 'failed' | 'cancelled'>(
  'idle',
)
const progressPercentage = ref<number | null>(null)
const segments = ref<TranscriptionSegment[]>([])
const playerRef = ref<InstanceType<typeof VideoPlayer> | null>(null)
const segmentContainerRef = ref<HTMLElement | null>(null)
const showSourceDialog = ref(true)
const currentPlaybackTime = ref(0)
const autoFollowActiveSegment = ref(true)
const pausedActiveSegmentIndex = ref<number | null>(null)
const showResumeFollowButton = ref(false)
const targetLang = ref('zh')

loadSettings().then((s) => {
  targetLang.value = s.defaultTranslateLang || 'zh'
})
const segmentRefs: Record<number, HTMLElement | null> = {}
let transcriptionSource: EventSource | null = null
let isProgrammaticScroll = false
let programmaticScrollTimer: ReturnType<typeof setTimeout> | null = null

const hasResolvedStream = computed(() => !!resolvedStream.value)

const videoSrc = computed(() => {
  if (!resolvedStream.value) return ''
  const { video } = resolvedStream.value
  return video.requires_relay ? getRelayedUrl(video.url, video.headers) : video.url
})

const audioSrc = computed(() => {
  if (!resolvedStream.value) return ''
  if (resolvedStream.value.video.has_audio) return ''
  const { audio } = resolvedStream.value
  return audio.requires_relay ? getRelayedUrl(audio.url, audio.headers) : audio.url
})

const videoSourceType = computed<'file' | 'hls'>(() => {
  if (!resolvedStream.value) return 'file'
  const sourceUrl = resolvedStream.value.video.url.toLowerCase()
  const protocol = String(resolvedStream.value.video.protocol ?? '').toLowerCase()
  const ext = String(resolvedStream.value.video.ext ?? '').toLowerCase()
  const formatId = String(resolvedStream.value.video.format_id ?? '').toLowerCase()
  return sourceUrl.includes('.m3u8') ||
    formatId.includes('hls') ||
    formatId.includes('m3u8') ||
    protocol.includes('m3u8') ||
    ext === 'm3u8'
    ? 'hls'
    : 'file'
})

const audioSourceType = computed<'file' | 'hls'>(() => {
  if (!resolvedStream.value) return 'file'
  const sourceUrl = resolvedStream.value.audio.url.toLowerCase()
  const protocol = String(resolvedStream.value.audio.protocol ?? '').toLowerCase()
  const ext = String(resolvedStream.value.audio.ext ?? '').toLowerCase()
  const formatId = String(resolvedStream.value.audio.format_id ?? '').toLowerCase()
  return sourceUrl.includes('.m3u8') ||
    formatId.includes('hls') ||
    formatId.includes('m3u8') ||
    protocol.includes('m3u8') ||
    ext === 'm3u8'
    ? 'hls'
    : 'file'
})

const platformBadgeClass = computed(() => {
  if (resolvedStream.value?.platform === 'youtube') {
    return 'border-red-400/30 bg-red-500/10 text-red-100'
  }
  return 'border-sky-400/30 bg-sky-500/10 text-sky-100'
})

const statusToneClass = computed(() => {
  switch (transcriptionStatus.value) {
    case 'running':
      return 'border-cyan-400/30 bg-cyan-500/10 text-cyan-100'
    case 'completed':
      return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-100'
    case 'failed':
      return 'border-rose-400/30 bg-rose-500/10 text-rose-100'
    case 'cancelled':
      return 'border-amber-400/30 bg-amber-500/10 text-amber-100'
    default:
      return 'border-slate-500/30 bg-slate-500/10 text-slate-200'
  }
})

const statusLabel = computed(() => {
  if (transcriptionStatus.value === 'running') return t('transcriptionProgress')
  if (transcriptionStatus.value === 'completed') return t('completed')
  if (transcriptionStatus.value === 'failed') return t('failed')
  if (transcriptionStatus.value === 'cancelled') return t('stopTranscription')
  return '待开始'
})

const progressLabel = computed(() => {
  if (progressPercentage.value !== null) {
    return `${Math.round(progressPercentage.value)}%`
  }
  return statusLabel.value
})

const playbackSegmentIndex = computed(() => {
  if (!segments.value.length) return null

  let closestIndex = 0
  let closestDistance = Number.POSITIVE_INFINITY

  for (let index = 0; index < segments.value.length; index += 1) {
    const segment = segments.value[index]
    if (currentPlaybackTime.value >= segment.start && currentPlaybackTime.value <= segment.end) {
      return index
    }

    const distance =
      currentPlaybackTime.value < segment.start
        ? segment.start - currentPlaybackTime.value
        : currentPlaybackTime.value - segment.end

    if (distance < closestDistance) {
      closestDistance = distance
      closestIndex = index
    }
  }

  return closestIndex
})

const activeSegmentIndex = computed(() =>
  autoFollowActiveSegment.value ? playbackSegmentIndex.value : pausedActiveSegmentIndex.value,
)

function formatTime(seconds: number) {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, seconds) : 0
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const secs = Math.floor(safeSeconds % 60)

  if (hours > 0) {
    return [hours, minutes, secs].map((value) => String(value).padStart(2, '0')).join(':')
  }

  return [minutes, secs].map((value) => String(value).padStart(2, '0')).join(':')
}

function closeTranscriptionSource() {
  if (transcriptionSource) {
    transcriptionSource.close()
    transcriptionSource = null
  }
}

function cancelProgrammaticScrollTimer() {
  if (programmaticScrollTimer) {
    clearTimeout(programmaticScrollTimer)
    programmaticScrollTimer = null
  }
}

function isElementFullyVisible(el: HTMLElement, container: HTMLElement) {
  const containerRect = container.getBoundingClientRect()
  const elementRect = el.getBoundingClientRect()
  return elementRect.top >= containerRect.top && elementRect.bottom <= containerRect.bottom
}

function scrollSegmentIntoView(index: number | null) {
  if (index === null) return

  const container = segmentContainerRef.value
  const target = segmentRefs[index]
  if (!container || !target) return
  if (isElementFullyVisible(target, container)) return

  isProgrammaticScroll = true
  cancelProgrammaticScrollTimer()
  target.scrollIntoView({
    behavior: 'smooth',
    block: 'center',
    inline: 'nearest',
  })

  programmaticScrollTimer = setTimeout(() => {
    isProgrammaticScroll = false
  }, 450)
}

function resetTranscriptionState() {
  closeTranscriptionSource()
  cancelProgrammaticScrollTimer()
  isProgrammaticScroll = false
  taskId.value = ''
  transcriptionStatus.value = 'idle'
  progressPercentage.value = null
  transcriptionError.value = ''
  segments.value = []
  currentPlaybackTime.value = 0
  autoFollowActiveSegment.value = true
  pausedActiveSegmentIndex.value = null
  showResumeFollowButton.value = false
  Object.keys(segmentRefs).forEach((key) => {
    delete segmentRefs[Number(key)]
  })
}

function normalizeSegment(
  segment: Record<string, unknown>,
  fallbackIndex: number,
): TranscriptionSegment | null {
  const text = typeof segment.text === 'string' ? segment.text.trim() : ''
  if (!text) return null

  const start = Number(segment.start ?? segment.start_time ?? segment.begin ?? 0)
  const end = Number(segment.end ?? segment.end_time ?? segment.stop ?? start)
  const index = Number(segment.index ?? segment.id ?? fallbackIndex)
  const translation = typeof segment.translation === 'string' ? segment.translation : undefined

  return {
    index: Number.isFinite(index) ? index : fallbackIndex,
    text,
    start: Number.isFinite(start) ? start : 0,
    end: Number.isFinite(end) ? end : Number.isFinite(start) ? start : 0,
    ...(translation ? { translation } : {}),
  }
}

function mergeSegments(nextSegments: TranscriptionSegment[]) {
  if (!nextSegments.length) return

  const merged = new Map(segments.value.map((segment) => [segment.index, segment]))
  nextSegments.forEach((segment) => {
    merged.set(segment.index, segment)
  })

  segments.value = Array.from(merged.values()).sort((a, b) => {
    if (a.index !== b.index) return a.index - b.index
    return a.start - b.start
  })

  nextTick(() => {
    if (autoFollowActiveSegment.value) {
      scrollSegmentIntoView(activeSegmentIndex.value)
    }
  })
}

function applyProgressFromPayload(payload: Record<string, unknown>) {
  if (typeof payload.percent === 'number') {
    progressPercentage.value = Math.max(0, Math.min(100, payload.percent))
    return
  }

  if (typeof payload.progress === 'number') {
    progressPercentage.value = Math.max(0, Math.min(100, payload.progress))
    return
  }

  const completed = Number(payload.completed_segments ?? payload.completed_entries)
  const total = Number(payload.total_segments ?? payload.total_entries)

  if (Number.isFinite(completed) && Number.isFinite(total) && total > 0) {
    progressPercentage.value = Math.max(0, Math.min(100, (completed / total) * 100))
  }
}

function handleSsePayload(payload: Record<string, unknown>) {
  applyProgressFromPayload(payload)

  const incoming = Array.isArray(payload.segments)
    ? payload.segments
    : Array.isArray(payload.entries)
      ? payload.entries
      : Array.isArray(payload.subtitle_entries)
        ? payload.subtitle_entries
        : payload.segment
          ? [payload.segment]
          : typeof payload.text === 'string'
            ? [payload]
            : []

  const normalized = incoming
    .map((segment, index) =>
      normalizeSegment(segment as Record<string, unknown>, segments.value.length + index + 1),
    )
    .filter((segment): segment is TranscriptionSegment => segment !== null)

  mergeSegments(normalized)

  const status = typeof payload.status === 'string' ? payload.status.toLowerCase() : ''
  if (status.includes('complete')) {
    transcriptionStatus.value = 'completed'
    progressPercentage.value = 100
    closeTranscriptionSource()
  } else if (status.includes('fail') || status.includes('error')) {
    transcriptionStatus.value = 'failed'
    transcriptionError.value = String(payload.message || payload.error || t('operationFailed'))
    closeTranscriptionSource()
  } else if (status.includes('cancel')) {
    transcriptionStatus.value = 'cancelled'
    closeTranscriptionSource()
  }
}

function handleTimeUpdate(time: number) {
  currentPlaybackTime.value = time
}

function seekToSegment(segment: TranscriptionSegment, index: number) {
  pausedActiveSegmentIndex.value = index
  currentPlaybackTime.value = segment.start
  playerRef.value?.seek(segment.start)
}

function isActiveSegment(index: number) {
  return activeSegmentIndex.value === index
}

function handleSegmentScroll() {
  if (isProgrammaticScroll) return
  if (!segments.value.length) return
  if (!autoFollowActiveSegment.value) return

  autoFollowActiveSegment.value = false
  pausedActiveSegmentIndex.value = playbackSegmentIndex.value
  showResumeFollowButton.value = true
}

function resumeAutoFollow() {
  autoFollowActiveSegment.value = true
  pausedActiveSegmentIndex.value = playbackSegmentIndex.value
  showResumeFollowButton.value = false

  nextTick(() => {
    scrollSegmentIntoView(playbackSegmentIndex.value)
  })
}

watch(playbackSegmentIndex, (nextIndex) => {
  if (!autoFollowActiveSegment.value) return
  pausedActiveSegmentIndex.value = nextIndex

  nextTick(() => {
    scrollSegmentIntoView(nextIndex)
  })
})

function attachTranscriptionStream(nextTaskId: string) {
  closeTranscriptionSource()
  const source = connectTranscriptionSSE(nextTaskId)
  transcriptionSource = source

  const consumeEvent = (event: MessageEvent) => {
    if (!event.data) return
    try {
      handleSsePayload(JSON.parse(event.data))
    } catch (error) {
      console.error('Failed to parse transcription event:', error)
    }
  }

  source.onmessage = consumeEvent
  source.addEventListener('progress', consumeEvent)
  source.addEventListener('segment', consumeEvent)
  source.addEventListener('end', consumeEvent)
  source.addEventListener('complete', consumeEvent)
  source.addEventListener('error', consumeEvent)
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED && transcriptionStatus.value === 'running') {
      transcriptionStatus.value = 'failed'
      transcriptionError.value = t('requestFailed')
      closeTranscriptionSource()
    }
  }
}

async function stopActiveTask() {
  if (!taskId.value) return

  try {
    await cancelTranscription(taskId.value)
  } catch (error) {
    console.error('Failed to cancel transcription:', error)
    transcriptionError.value = error instanceof Error ? error.message : t('requestFailed')
  } finally {
    closeTranscriptionSource()
  }
}

async function handleResolve() {
  const targetUrl = streamUrl.value.trim()
  if (!targetUrl) {
    resolveError.value = t('pleaseEnterUrl')
    return
  }

  resolving.value = true
  resolveError.value = ''
  transcriptionError.value = ''

  if (transcriptionStatus.value === 'running') {
    await stopActiveTask()
  }

  resetTranscriptionState()

  try {
    resolvedStream.value = await resolveStream(targetUrl)
    showSourceDialog.value = false
  } catch (error) {
    console.error('Failed to resolve stream:', error)
    resolvedStream.value = null
    resolveError.value = error instanceof Error ? error.message : t('requestFailed')
  } finally {
    resolving.value = false
  }
}

async function handleStartTranscription() {
  if (!resolvedStream.value || startingTranscription.value) return

  startingTranscription.value = true
  transcriptionError.value = ''
  segments.value = []
  progressPercentage.value = null
  transcriptionStatus.value = 'running'

  try {
    const nextTaskId = await startTranscription(
      resolvedStream.value.audio.url,
      resolvedStream.value.audio.headers,
      resolvedStream.value.audio.requires_relay,
      'en',
      targetLang.value,
    )
    taskId.value = nextTaskId
    attachTranscriptionStream(nextTaskId)
  } catch (error) {
    console.error('Failed to start transcription:', error)
    transcriptionStatus.value = 'failed'
    transcriptionError.value = error instanceof Error ? error.message : t('requestFailed')
  } finally {
    startingTranscription.value = false
  }
}

async function handleCancel() {
  if (!taskId.value) return

  try {
    await cancelTranscription(taskId.value)
  } catch (error) {
    console.error('Failed to cancel transcription:', error)
    transcriptionError.value = error instanceof Error ? error.message : t('requestFailed')
  } finally {
    closeTranscriptionSource()
    transcriptionStatus.value = 'cancelled'
    progressPercentage.value = null
    taskId.value = ''
  }
}

onBeforeUnmount(async () => {
  cancelProgrammaticScrollTimer()
  isProgrammaticScroll = false
  if (transcriptionStatus.value === 'running' && taskId.value) {
    await stopActiveTask()
  }
  closeTranscriptionSource()
})
</script>

<template>
  <div class="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.16),_transparent_28%),radial-gradient(circle_at_bottom_right,_rgba(59,130,246,0.2),_transparent_34%),linear-gradient(145deg,#020617_0%,#0f172a_48%,#13253f_100%)] text-white">
    <div class="mx-auto flex w-full max-w-[1600px] flex-col gap-6 px-6 py-6">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.34em] text-cyan-200/80">
            Live Media Transcription
          </p>
          <h1 class="mt-2 text-3xl font-semibold tracking-tight text-white">
            {{ t('streamTranscription') }}
          </h1>
        </div>

        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-white/12 bg-slate-950/35 px-4 py-2.5 text-sm font-medium text-slate-100 shadow-[0_14px_32px_rgba(2,6,23,0.28)] backdrop-blur-md transition hover:border-cyan-300/35 hover:bg-slate-900/65"
          @click="showSourceDialog = true"
        >
          <Settings2 class="h-4 w-4" />
          源配置
        </button>
      </div>

      <div class="flex h-[calc(100vh-160px)] max-h-[calc(100vh-160px)] items-stretch gap-6 min-w-0">
        <section class="flex-[2] min-w-0 min-h-0">
          <div class="flex h-full flex-col gap-5 rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(15,23,42,0.74))] p-5 shadow-[0_30px_80px_rgba(2,6,23,0.45)] backdrop-blur-xl">
            <div class="flex items-center justify-between gap-4 rounded-2xl border border-white/8 bg-slate-950/28 px-4 py-3">
              <div class="min-w-0">
                <p class="text-xs uppercase tracking-[0.28em] text-slate-400">Playback</p>
                <h2 class="truncate text-lg font-semibold text-white">
                  {{ resolvedStream?.title || '等待解析视频源' }}
                </h2>
              </div>

              <div class="flex shrink-0 items-center gap-2">
                <div
                  v-if="resolvedStream"
                  class="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.24em]"
                  :class="platformBadgeClass"
                >
                  <Radio class="h-3.5 w-3.5" />
                  {{ resolvedStream.platform }}
                </div>
                <div
                  class="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold"
                  :class="statusToneClass"
                >
                  <Waves class="h-3.5 w-3.5" />
                  {{ statusLabel }}
                </div>
              </div>
            </div>

            <div class="flex-1 min-h-0 rounded-[24px] border border-white/10 bg-slate-950/60 p-4">
              <div class="relative h-full overflow-hidden rounded-[18px] border border-slate-700/70 bg-black/70">
                <VideoPlayer
                  v-if="resolvedStream && videoSrc"
                  ref="playerRef"
                  :key="`${videoSourceType}:${videoSrc}`"
                  :src="videoSrc"
                  :source-type="videoSourceType"
                  :audio-src="audioSrc || undefined"
                  :audio-source-type="audioSourceType"
                  class="absolute inset-0 h-full w-full"
                  @time-update="handleTimeUpdate"
                />

                <div
                  v-else
                  class="flex h-full items-center justify-center px-8 text-center text-sm text-slate-400"
                >
                  <div class="space-y-4">
                    <p>打开“源配置”，填写流媒体 URL 后解析。</p>
                    <button
                      type="button"
                      class="inline-flex items-center gap-2 rounded-full border border-cyan-300/25 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:bg-cyan-500/20"
                      @click="showSourceDialog = true"
                    >
                      <Link2 class="h-4 w-4" />
                      配置流媒体源
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <aside class="flex-[1] min-w-[360px] max-w-[480px] min-h-0 self-stretch">
          <div class="flex h-full min-h-0 max-h-full flex-col overflow-hidden rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.94),rgba(15,23,42,0.8))] p-5 shadow-[0_30px_80px_rgba(2,6,23,0.42)] backdrop-blur-xl">
            <div class="flex items-start justify-between gap-4 border-b border-white/8 pb-4">
              <div>
                <p class="text-xs uppercase tracking-[0.26em] text-slate-400">Recognition</p>
                <h2 class="mt-2 text-xl font-semibold text-white">字幕识别 / 字幕列表</h2>
                <p class="mt-1 text-sm text-slate-400">
                  {{ segments.length ? `已接收 ${segments.length} 条字幕` : t('noTranscriptionYet') }}
                </p>
              </div>

              <div class="flex shrink-0 flex-wrap gap-2">
                <button
                  type="button"
                  :disabled="!resolvedStream || startingTranscription || transcriptionStatus === 'running'"
                  class="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
                  @click="handleStartTranscription"
                >
                  {{
                    startingTranscription || transcriptionStatus === 'running'
                      ? t('transcriptionProgress')
                      : t('startTranscription')
                  }}
                </button>

                <button
                  v-if="transcriptionStatus === 'running'"
                  type="button"
                  class="rounded-xl border border-rose-400/35 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/18"
                  @click="handleCancel"
                >
                  {{ t('stopTranscription') }}
                </button>
              </div>
            </div>

            <div class="mt-4 shrink-0 space-y-4">
              <div class="rounded-2xl border border-white/8 bg-slate-950/32 p-4">
                <div class="mb-2 flex items-center justify-between text-sm text-slate-300">
                  <span>{{ t('transcriptionProgress') }}</span>
                  <span>{{ progressLabel }}</span>
                </div>

                <div class="h-2.5 overflow-hidden rounded-full bg-slate-950/90">
                  <div
                    class="h-full rounded-full bg-[linear-gradient(90deg,#06b6d4_0%,#38bdf8_50%,#34d399_100%)] transition-all duration-300"
                    :class="progressPercentage === null && transcriptionStatus === 'running' ? 'w-1/3 animate-pulse' : ''"
                    :style="progressPercentage !== null ? { width: `${progressPercentage}%` } : undefined"
                  />
                </div>
              </div>

              <div
                v-if="resolvedStream"
                class="grid gap-3 rounded-2xl border border-white/8 bg-slate-950/25 p-4"
              >
                <div class="flex items-center gap-3 text-sm text-slate-200">
                  <Clock3 class="h-4 w-4 text-cyan-200" />
                  <span>{{ t('duration') }}: {{ formatTime(resolvedStream.duration) }}</span>
                </div>
                <div class="truncate text-sm text-slate-300">
                  {{ resolvedStream.title }}
                </div>
              </div>
            </div>

            <div class="relative mt-4 min-h-0 flex-1 overflow-hidden rounded-[22px] border border-white/8 bg-slate-950/34">
              <div
                ref="segmentContainerRef"
                class="h-full min-h-0 overflow-y-auto p-4"
                @scroll.passive="handleSegmentScroll"
              >
                <div
                  v-if="!segments.length"
                  class="flex min-h-[320px] items-center justify-center px-6 text-center text-sm text-slate-400"
                >
                  {{ t('noTranscriptionYet') }}
                </div>

                <div v-else class="space-y-3">
                  <button
                    v-for="(segment, index) in segments"
                    :key="segment.index"
                    type="button"
                    :ref="
                      (el) => {
                        segmentRefs[index] = (el as HTMLElement | null) ?? null
                      }
                    "
                    class="block w-full rounded-2xl border p-4 text-left shadow-[0_12px_24px_rgba(2,6,23,0.18)] transition duration-200 hover:-translate-y-0.5 hover:border-cyan-300/30 hover:bg-slate-800/78"
                    :class="
                      isActiveSegment(index)
                        ? 'border-cyan-300/40 bg-cyan-500/12 ring-1 ring-cyan-300/25'
                        : 'border-white/8 bg-slate-800/55'
                    "
                    @click="seekToSegment(segment, index)"
                  >
                    <div class="mb-2 flex items-center justify-between gap-3 text-xs text-slate-400">
                      <span
                        class="font-medium"
                        :class="isActiveSegment(index) ? 'text-cyan-100' : 'text-cyan-200'"
                      >
                        {{ t('segmentIndex') }} {{ segment.index }}
                      </span>
                      <span>
                        {{ formatTime(segment.start) }} → {{ formatTime(segment.end) }}
                      </span>
                    </div>
                    <p
                      class="text-sm leading-6"
                      :class="isActiveSegment(index) ? 'text-white' : 'text-slate-100'"
                    >
                      {{ segment.text }}
                    </p>
                    <p
                      v-if="segment.translation"
                      class="mt-1 text-sm leading-6 text-cyan-200/70"
                    >
                      {{ segment.translation }}
                    </p>
                  </button>
                </div>
              </div>

              <button
                v-show="showResumeFollowButton"
                type="button"
                class="absolute bottom-5 right-5 flex h-11 w-11 items-center justify-center rounded-full border border-emerald-300/35 bg-emerald-500/75 text-white shadow-[0_16px_30px_rgba(16,185,129,0.28)] transition hover:bg-emerald-400/85"
                @click="resumeAutoFollow"
              >
                <ArrowBigDown class="h-5 w-5" />
              </button>
            </div>

            <div
              v-if="transcriptionError"
              class="mt-4 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100"
            >
              {{ transcriptionError }}
            </div>
          </div>
        </aside>
      </div>
    </div>

    <div
      v-if="showSourceDialog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/72 px-4 backdrop-blur-md"
      @click.self="showSourceDialog = false"
    >
      <div class="w-full max-w-2xl rounded-[30px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.96),rgba(15,23,42,0.86))] p-6 shadow-[0_40px_120px_rgba(2,6,23,0.55)]">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-200/75">
              Source Dialog
            </p>
            <h2 class="mt-2 text-2xl font-semibold text-white">流媒体源配置</h2>
            <p class="mt-1 text-sm text-slate-400">
              URL、缩略图和时长信息都集中在这里处理。
            </p>
          </div>

          <button
            type="button"
            class="rounded-full border border-white/10 bg-slate-900/55 p-2 text-slate-300 transition hover:bg-slate-800/80 hover:text-white"
            @click="showSourceDialog = false"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <form class="mt-6 space-y-4" @submit.prevent="handleResolve">
          <div class="relative">
            <Link2 class="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              v-model="streamUrl"
              :placeholder="t('enterVideoUrl')"
              class="w-full rounded-2xl border border-white/10 bg-slate-950/70 py-3.5 pl-11 pr-4 text-sm text-white outline-none transition focus:border-cyan-300/35 focus:ring-2 focus:ring-cyan-400/10"
            />
          </div>

          <div class="flex items-center gap-3">
            <span class="text-sm text-slate-400">实时翻译：</span>
            <select
              v-model="targetLang"
              class="appearance-none rounded-xl border border-white/10 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-300/35"
            >
              <option value="zh">→ 中文</option>
              <option value="en">→ English</option>
              <option value="jp">→ 日本語</option>
            </select>
            <span class="text-xs text-slate-500">默认取自「界面设置 → 默认译文语言」</span>
          </div>

          <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="text-sm text-slate-400">
              支持 YouTube / Bilibili 流媒体解析。
            </p>

            <button
              type="submit"
              :disabled="resolving"
              class="inline-flex min-w-36 items-center justify-center gap-2 rounded-2xl bg-cyan-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-55"
            >
              <ChevronRight class="h-4 w-4" />
              {{ resolving ? t('resolving') : t('resolve') }}
            </button>
          </div>
        </form>

        <p v-if="resolveError" class="mt-3 rounded-2xl border border-rose-400/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          {{ resolveError }}
        </p>

        <div
          v-if="resolvedStream"
          class="mt-6 grid gap-5 rounded-[24px] border border-white/8 bg-slate-950/38 p-4 md:grid-cols-[220px_minmax(0,1fr)]"
        >
          <div class="overflow-hidden rounded-2xl border border-white/8 bg-slate-900/75">
            <img
              v-if="resolvedStream.thumbnail"
              :src="resolvedStream.thumbnail"
              :alt="resolvedStream.title"
              class="h-full w-full object-cover"
            />
            <div
              v-else
              class="flex h-full min-h-[140px] items-center justify-center text-sm text-slate-500"
            >
              No thumbnail
            </div>
          </div>

          <div class="min-w-0 space-y-4">
            <div>
              <div
                class="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.24em]"
                :class="platformBadgeClass"
              >
                <Radio class="h-3.5 w-3.5" />
                {{ resolvedStream.platform }}
              </div>
              <h3 class="mt-3 text-lg font-semibold text-white">
                {{ resolvedStream.title }}
              </h3>
            </div>

            <div class="grid gap-3 sm:grid-cols-2">
              <div class="rounded-2xl border border-white/8 bg-slate-900/62 p-3">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">Duration</p>
                <p class="mt-2 text-sm font-medium text-slate-100">
                  {{ formatTime(resolvedStream.duration) }}
                </p>
              </div>
              <div class="rounded-2xl border border-white/8 bg-slate-900/62 p-3">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">Stream Type</p>
                <p class="mt-2 text-sm font-medium text-slate-100">
                  {{ videoSourceType.toUpperCase() }}
                </p>
              </div>
            </div>

            <div class="rounded-2xl border border-white/8 bg-slate-900/62 p-3">
              <p class="text-xs uppercase tracking-[0.22em] text-slate-500">URL</p>
              <p class="mt-2 break-all text-sm leading-6 text-slate-300">
                {{ streamUrl }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
