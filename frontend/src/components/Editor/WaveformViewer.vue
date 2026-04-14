<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Hide, View } from '@element-plus/icons-vue'
import { SlidersHorizontal } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import WaveSurfer from 'wavesurfer.js'
import WaveformOverlayTracks from './WaveformOverlayTracks.vue'
import WaveformRuler from './WaveformRuler.vue'
import { normalizePeaks } from '@/composables/peaks'
import type { Subtitle } from '@/types/subtitle'
import type { WaveformPeakData } from '@/composables/AudioWaveformAPI'
import { useWaveformPeaks } from '@/composables/AudioWaveformAPI'

const { t } = useI18n()

interface Props {
  rawSubtitles?: Subtitle[]
  foreignSubtitles?: Subtitle[]
  videoId?: number
  videoUrl?: string
  blobUrls?: (string | undefined)[]
  currentTime?: number
  duration?: number
  showRawTrack?: boolean
  showForeignTrack?: boolean
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  rawSubtitles: () => [],
  foreignSubtitles: () => [],
  currentTime: 0,
  duration: 30,
  showRawTrack: true,
  showForeignTrack: true,
  height: 32,
})

const emit = defineEmits<{
  (e: 'seek', t: number): void
  (e: 'update:showRawTrack', v: boolean): void
  (e: 'update:showForeignTrack', v: boolean): void
}>()

const zoom = ref(50)
const waveformModuleRef = ref<HTMLDivElement>()
const scrollContainer = ref<HTMLDivElement>()
const waveformContainer = ref<HTMLDivElement>()
const localScrollLeft = ref(0)
const viewportWidth = ref(0)
const waveformPeakData = ref<WaveformPeakData | null>(null)
const isWaveformLoading = ref(false)
const waveformLoadingMessage = ref('Loading waveform data...')
const toolbarRevealed = ref(false)

// --- Draggable toolbar position ---
const TOOLBAR_POS_KEY = 'waveform-toolbar-pos'
const toolbarPos = ref<{ x: number; y: number } | null>(null)
const isDragging = ref(false)
let wasDragged = false

function loadToolbarPos() {
  try {
    const raw = localStorage.getItem(TOOLBAR_POS_KEY)
    if (raw) toolbarPos.value = JSON.parse(raw)
  } catch {
    /* ignore */
  }
}

function saveToolbarPos() {
  if (toolbarPos.value) {
    localStorage.setItem(TOOLBAR_POS_KEY, JSON.stringify(toolbarPos.value))
  }
}

function toolbarPosStyle() {
  if (toolbarPos.value) {
    return { left: `${toolbarPos.value.x}px`, top: `${toolbarPos.value.y}px`, transform: 'translateX(-50%)' }
  }
  return {} // falls back to CSS centering
}

function onDragStart(event: MouseEvent) {
  if (!waveformModuleRef.value) return
  const parentRect = waveformModuleRef.value.getBoundingClientRect()

  // Current anchor point (center of trigger button)
  const anchorX = toolbarPos.value ? toolbarPos.value.x : parentRect.width / 2
  const anchorY = toolbarPos.value ? toolbarPos.value.y : 8

  // Offset from anchor to mouse
  const offsetX = event.clientX - parentRect.left - anchorX
  const offsetY = event.clientY - parentRect.top - anchorY

  isDragging.value = true
  wasDragged = false

  function onMove(e: MouseEvent) {
    const rect = waveformModuleRef.value?.getBoundingClientRect()
    if (!rect) return

    let newX = e.clientX - rect.left - offsetX
    let newY = e.clientY - rect.top - offsetY

    // Clamp within parent bounds (with 16px padding)
    const pad = 16
    newX = Math.max(pad, Math.min(rect.width - pad, newX))
    newY = Math.max(4, Math.min(rect.height - pad, newY))

    toolbarPos.value = { x: newX, y: newY }
    wasDragged = true
  }

  function onUp() {
    isDragging.value = false
    saveToolbarPos()
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function resetToolbarPos() {
  toolbarPos.value = null
  localStorage.removeItem(TOOLBAR_POS_KEY)
}

onMounted(() => {
  loadToolbarPos()
})

const trackHeight = 32
const rulerHeight = 28

const trackAreaHeight = computed(() => {
  let count = 0
  if (props.showRawTrack) count += 1
  if (props.showForeignTrack && props.foreignSubtitles.length > 0) count += 1
  return count * trackHeight
})

const pixelsPerSecond = computed(() => zoom.value)
const contentWidth = computed(() => props.duration * pixelsPerSecond.value)
const contentHeight = computed(() => rulerHeight + trackAreaHeight.value + props.height)
const hasWaveformData = computed(() => Boolean(waveformPeakData.value?.peaks?.length))

let ws: WaveSurfer | null = null
let waveformPeaksComposable: ReturnType<typeof useWaveformPeaks> | null = null
const stopComposableWatches: Array<() => void> = []

function onContainerScroll() {
  if (!scrollContainer.value) return
  localScrollLeft.value = scrollContainer.value.scrollLeft
}

function revealToolbar() {
  toolbarRevealed.value = true
}

function isFocusWithinModule() {
  const activeElement = document.activeElement
  return activeElement instanceof Node && waveformModuleRef.value?.contains(activeElement)
}

function concealToolbar() {
  if (isFocusWithinModule()) return
  toolbarRevealed.value = false
}

function toggleToolbar() {
  toolbarRevealed.value = !toolbarRevealed.value
}

function handleToolbarFocusOut(event: FocusEvent) {
  const nextTarget = event.relatedTarget

  if (nextTarget instanceof Node && waveformModuleRef.value?.contains(nextTarget)) {
    return
  }

  concealToolbar()
}

function updateViewportWidth() {
  viewportWidth.value = scrollContainer.value?.clientWidth ?? 0
}

function destroyWaveSurfer() {
  ws?.destroy()
  ws = null
}

function initWaveSurfer() {
  destroyWaveSurfer()

  if (isWaveformLoading.value || !waveformContainer.value || !hasWaveformData.value) return

  const rawPeaks = waveformPeakData.value?.peaks
  const peaksArray = normalizePeaks(rawPeaks)
  const dur = Number(waveformPeakData.value?.duration ?? props.duration ?? 0)

  if (!dur || !Number.isFinite(dur)) return

  ws = WaveSurfer.create({
    container: waveformContainer.value,
    height: props.height,
    waveColor: '#64748b',
    progressColor: '#34d399',
    cursorColor: '#fb7185',
    barWidth: 1.5,
    barGap: 0.5,
    barRadius: 0.5,
    barHeight: 0.6,
    normalize: true,
    mediaControls: false,
    minPxPerSec: zoom.value,
    peaks: [peaksArray],
    duration: dur,
    fillParent: false,
    hideScrollbar: true,
    autoCenter: false,
    autoScroll: false,
  })

  ws.on('ready', () => {
    if (!ws) return

    ws.zoom(zoom.value)
    updateViewportWidth()
  })

  ws.on('interaction', (t) => emit('seek', t))
}

watch(zoom, (newZoom) => {
  if (!ws) return

  ws.zoom(newZoom)
  requestAnimationFrame(() => {
    updateViewportWidth()
  })
})

watch(
  () => props.duration,
  () => {
    if (!hasWaveformData.value) return
    nextTick(() => initWaveSurfer())
  },
)

watch(
  () => props.currentTime,
  (t) => {
    if (!ws || !props.duration) return

    const pct = t / props.duration
    if (Math.abs(ws.getCurrentTime() - t) > 0.05) ws.seekTo(pct)

    if (scrollContainer.value) {
      const playheadPos = t * pixelsPerSecond.value
      const containerWidth = scrollContainer.value.clientWidth
      const currentScroll = scrollContainer.value.scrollLeft

      if (playheadPos < currentScroll || playheadPos > currentScroll + containerWidth - 50) {
        scrollContainer.value.scrollLeft = Math.max(0, playheadPos - containerWidth / 2)
      }
    }
  },
)

onMounted(async () => {
  await nextTick()
  updateViewportWidth()

  if (props.videoId && props.videoUrl) {
    waveformPeaksComposable = useWaveformPeaks(props.videoId, props.videoUrl)

    stopComposableWatches.push(
      watch(
        waveformPeaksComposable.waveformPeaks,
        (value) => {
          waveformPeakData.value = value

          if (value) {
            nextTick(() => initWaveSurfer())
          }
        },
        { immediate: true },
      ),
    )

    stopComposableWatches.push(
      watch(
        waveformPeaksComposable.isLoading,
        (value) => {
          isWaveformLoading.value = value

          if (!value && waveformPeakData.value) {
            nextTick(() => initWaveSurfer())
          }
        },
        { immediate: true },
      ),
    )

    stopComposableWatches.push(
      watch(
        waveformPeaksComposable.loadingMessage,
        (value) => {
          waveformLoadingMessage.value = value
        },
        { immediate: true },
      ),
    )

    await waveformPeaksComposable.initialize()
    return
  }

  initWaveSurfer()
})

onBeforeUnmount(() => {
  destroyWaveSurfer()
  stopComposableWatches.forEach((stop) => stop())
  waveformPeaksComposable?.cleanup()
})
</script>

<template>
  <div
    ref="waveformModuleRef"
    class="relative w-full self-start rounded-[4px] bg-gradient-to-b from-slate-900/18 via-slate-950/[0.05] to-transparent px-1 pb-1 pt-2"
    :class="{ 'select-none': isDragging }"
    @focusin="revealToolbar"
    @focusout="handleToolbarFocusOut"
  >
    <div
      class="pointer-events-none absolute inset-x-1 top-0 h-8 rounded-t-[4px] bg-gradient-to-b from-white/[0.02] via-white/[0.008] to-transparent"
    ></div>

    <div
      class="absolute z-30 flex flex-col items-center gap-1"
      :class="toolbarPos ? '' : 'left-1/2 top-2 -translate-x-1/2'"
      :style="toolbarPosStyle()"
    >
      <button
        type="button"
        class="flex h-7 items-center justify-center gap-2 rounded-full border border-white/[0.08] bg-slate-950/30 px-2.5 text-slate-300/70 shadow-sm shadow-black/10 backdrop-blur-sm transition-all duration-200 hover:border-white/[0.14] hover:bg-slate-950/42 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300/40"
        :class="isDragging ? 'cursor-grabbing' : 'cursor-grab'"
        :aria-expanded="toolbarRevealed"
        aria-label="Drag to move, click to reveal waveform controls"
        @mouseenter="!isDragging && revealToolbar()"
        @click="!isDragging && !wasDragged && toggleToolbar()"
        @mousedown="onDragStart"
        @dblclick="resetToolbarPos"
      >
        <SlidersHorizontal class="h-3.5 w-3.5" />
      </button>

      <div
        class="relative flex min-w-[270px] flex-col gap-3 rounded-[18px] border border-white/[0.08] bg-slate-950/58 px-3 py-2.5 shadow-[0_18px_40px_rgba(2,6,23,0.28)] backdrop-blur-xl transition-all duration-200"
        :class="
          toolbarRevealed
            ? 'translate-y-0 scale-100 opacity-100'
            : 'pointer-events-none -translate-y-1 scale-[0.985] opacity-0'
        "
        @mouseenter="revealToolbar"
        @mouseleave="concealToolbar"
      >
        <div
          class="pointer-events-none absolute inset-x-0 top-0 h-10 rounded-t-[18px] bg-gradient-to-b from-white/[0.05] via-white/[0.015] to-transparent"
        ></div>

        <div class="flex items-center gap-3">
          <span
            class="whitespace-nowrap text-[9px] font-semibold uppercase tracking-[0.22em] text-slate-500"
          >
            {{ t('zoom') }}
          </span>
          <el-slider
            v-model="zoom"
            class="toolbar-slider min-w-0 flex-1"
            :min="10"
            :max="500"
            size="small"
          />
          <span class="min-w-[2.5rem] text-right text-[11px] font-medium text-slate-300/90">{{
            zoom
          }}</span>
        </div>

        <div class="flex items-center gap-2">
          <el-tooltip
            :content="props.showRawTrack ? '隐藏原文轨道' : '显示原文轨道'"
            placement="top"
          >
            <button
              type="button"
              class="flex flex-1 items-center justify-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-medium transition-all"
              :class="
                props.showRawTrack
                  ? 'border-amber-300/28 bg-amber-300/10 text-amber-100'
                  : 'border-white/[0.08] bg-white/[0.04] text-slate-400 hover:border-white/[0.14] hover:text-slate-200'
              "
              @click="emit('update:showRawTrack', !props.showRawTrack)"
            >
              <el-icon size="14"><View v-if="props.showRawTrack" /><Hide v-else /></el-icon>
              <span>Raw</span>
            </button>
          </el-tooltip>

          <el-tooltip
            :content="props.showForeignTrack ? '隐藏译文轨道' : '显示译文轨道'"
            placement="top"
          >
            <button
              type="button"
              class="flex flex-1 items-center justify-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-medium transition-all"
              :class="
                props.showForeignTrack
                  ? 'border-sky-300/28 bg-sky-300/10 text-sky-100'
                  : 'border-white/[0.08] bg-white/[0.04] text-slate-400 hover:border-white/[0.14] hover:text-slate-200'
              "
              @click="emit('update:showForeignTrack', !props.showForeignTrack)"
            >
              <el-icon size="14"><View v-if="props.showForeignTrack" /><Hide v-else /></el-icon>
              <span>Foreign</span>
            </button>
          </el-tooltip>
        </div>
      </div>
    </div>

    <div
      ref="scrollContainer"
      class="scrollbar-hidden relative overflow-x-auto overflow-y-hidden rounded-[4px] border border-white/[0.02] bg-transparent"
      :style="{ height: `${contentHeight}px` }"
      @scroll="onContainerScroll"
    >
      <div
        class="pointer-events-none absolute inset-0 rounded-[4px] bg-gradient-to-b from-white/[0.012] via-transparent to-slate-950/[0.06]"
      ></div>

      <div
        v-if="isWaveformLoading"
        class="absolute inset-0 z-20 flex items-center justify-center rounded-[4px] bg-slate-950/35 backdrop-blur-sm"
      >
        <div class="text-center">
          <div
            class="mb-3 inline-block h-8 w-8 animate-spin rounded-full border-b-2 border-green-500"
          ></div>
          <p class="text-sm text-slate-400">
            {{ waveformLoadingMessage || 'Loading waveform data...' }}
          </p>
        </div>
      </div>

      <div
        v-else-if="!hasWaveformData"
        class="absolute inset-0 z-10 flex items-center justify-center rounded-[4px] bg-slate-950/12"
      >
        <p class="text-sm text-slate-400">No waveform data available</p>
      </div>

      <div
        class="relative inline-block min-w-full align-top"
        :style="{ width: `${contentWidth}px`, minWidth: '100%' }"
      >
        <WaveformRuler
          :duration="props.duration"
          :pixels-per-second="pixelsPerSecond"
          :content-width="contentWidth"
          :current-time="props.currentTime"
          :height="rulerHeight"
        />

        <WaveformOverlayTracks
          :duration="props.duration"
          :pixels-per-second="pixelsPerSecond"
          :scroll-left="localScrollLeft"
          :viewport-width="viewportWidth"
          :current-time="props.currentTime"
          :raw-subtitles="props.rawSubtitles"
          :foreign-subtitles="props.foreignSubtitles"
          :show-raw-track="props.showRawTrack"
          :show-foreign-track="props.showForeignTrack"
          :track-height="trackHeight"
          @seek="(t) => emit('seek', t)"
        />
        
        <div
          class="relative overflow-hidden border-t border-white/[0.04] bg-gradient-to-b from-white/[0.015] via-slate-950/[0.02] to-transparent"
          :style="{ height: `${props.height}px` }"
        >
          <div
            ref="waveformContainer"
            class="waveform-container relative z-0 w-full overflow-hidden"
            :style="{ height: `${props.height}px` }"
          ></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.waveform-container) {
  height: 100% !important;
  overflow: hidden;
}

:deep(.waveform-container > *) {
  height: 100% !important;
  max-height: 100% !important;
}

:deep(.waveform-container canvas) {
  max-height: 100% !important;
}

.toolbar-slider :deep(.el-slider__runway) {
  background-color: rgba(148, 163, 184, 0.16);
}

.toolbar-slider :deep(.el-slider__bar) {
  background: linear-gradient(90deg, rgba(74, 222, 128, 0.82), rgba(52, 211, 153, 0.96));
}

.toolbar-slider :deep(.el-slider__button) {
  border-color: rgba(167, 243, 208, 0.95);
  background-color: rgba(240, 253, 250, 0.98);
}

.toolbar-slider :deep(.el-slider__button-wrapper) {
  width: 30px;
  height: 30px;
}
</style>
