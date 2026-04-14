<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Subtitle } from '@/types/subtitle'
import WaveformSubtitleBlock from './WaveformSubtitleBlock.vue'

interface Props {
  duration: number
  pixelsPerSecond: number
  scrollLeft: number
  viewportWidth: number
  currentTime: number
  rawSubtitles: Subtitle[]
  foreignSubtitles: Subtitle[]
  showRawTrack: boolean
  showForeignTrack: boolean
  rawTrackLabel?: string
  foreignTrackLabel?: string
  trackHeight?: number
}

interface VisibleSubtitleBlock {
  subtitle: Subtitle
  leftPx: number
  widthPx: number
  isCurrent: boolean
}

interface TrackConfig {
  key: 'raw' | 'foreign'
  label: string
  markerColor: string
}

const props = withDefaults(defineProps<Props>(), {
  rawTrackLabel: '原文',
  foreignTrackLabel: '译文',
  trackHeight: 40,
})

const emit = defineEmits<{
  (e: 'seek', time: number): void
}>()

const safePixelsPerSecond = computed(() => Math.max(props.pixelsPerSecond, 0))

const contentWidth = computed(() => props.duration * safePixelsPerSecond.value)

const overscanSec = computed(() => {
  if (safePixelsPerSecond.value <= 0) {
    return 0
  }
  return props.viewportWidth / safePixelsPerSecond.value
})

const visibleStart = computed(() => {
  if (safePixelsPerSecond.value <= 0) {
    return 0
  }
  return Math.max(0, props.scrollLeft / safePixelsPerSecond.value - overscanSec.value)
})

const visibleEnd = computed(() => {
  if (safePixelsPerSecond.value <= 0) {
    return 0
  }
  return Math.min(
    props.duration,
    (props.scrollLeft + props.viewportWidth) / safePixelsPerSecond.value + overscanSec.value,
  )
})

function createVisibleBlocks(subtitles: Subtitle[]): VisibleSubtitleBlock[] {
  return subtitles
    .filter((subtitle) => subtitle.end >= visibleStart.value && subtitle.start <= visibleEnd.value)
    .map((subtitle) => ({
      subtitle,
      leftPx: subtitle.start * safePixelsPerSecond.value,
      widthPx: Math.max(0, (subtitle.end - subtitle.start) * safePixelsPerSecond.value),
      isCurrent: props.currentTime >= subtitle.start && props.currentTime <= subtitle.end,
    }))
}

const visibleRawBlocks = computed(() => createVisibleBlocks(props.rawSubtitles))

const visibleForeignBlocks = computed(() => createVisibleBlocks(props.foreignSubtitles))

const blockMap = computed<Record<'raw' | 'foreign', VisibleSubtitleBlock[]>>(() => ({
  raw: visibleRawBlocks.value,
  foreign: visibleForeignBlocks.value,
}))

const tracks = computed<TrackConfig[]>(() => {
  const nextTracks: TrackConfig[] = []

  if (props.showRawTrack) {
    nextTracks.push({
      key: 'raw',
      label: props.rawTrackLabel,
      markerColor: '#facc15',
    })
  }

  if (props.showForeignTrack && props.foreignSubtitles.length > 0) {
    nextTracks.push({
      key: 'foreign',
      label: props.foreignTrackLabel,
      markerColor: '#38bdf8',
    })
  }

  return nextTracks
})

const visibleTrackCount = computed(() => tracks.value.length)

const totalHeight = computed(() => visibleTrackCount.value * props.trackHeight)

const playheadLeft = computed(() => {
  return props.currentTime * safePixelsPerSecond.value
})

function handleSeek(time: number) {
  emit('seek', time)
}

// --- Playhead drag-to-scrub ---
const overlayRef = ref<HTMLDivElement>()
const isDraggingPlayhead = ref(false)

function onPlayheadDragStart(event: MouseEvent) {
  event.preventDefault()
  isDraggingPlayhead.value = true

  function onMove(e: MouseEvent) {
    const el = overlayRef.value
    if (!el || safePixelsPerSecond.value <= 0) return

    const rect = el.getBoundingClientRect()
    const x = e.clientX - rect.left
    const time = Math.max(0, Math.min(props.duration, x / safePixelsPerSecond.value))
    emit('seek', time)
  }

  function onUp() {
    isDraggingPlayhead.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }

  // Also emit initial position in case mousedown was slightly off the line
  onMove(event)

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// Click on empty area to seek
function onOverlayClick(event: MouseEvent) {
  if (isDraggingPlayhead.value) return
  const el = overlayRef.value
  if (!el || safePixelsPerSecond.value <= 0) return

  const rect = el.getBoundingClientRect()
  const x = event.clientX - rect.left
  const time = Math.max(0, Math.min(props.duration, x / safePixelsPerSecond.value))
  emit('seek', time)
}
</script>

<template>
  <div
    ref="overlayRef"
    class="overlay-container"
    :class="{ 'is-dragging': isDraggingPlayhead }"
    :style="{
      width: `${contentWidth}px`,
      height: `${totalHeight}px`,
    }"
    @click="onOverlayClick"
  >
    <div
      v-for="track in tracks"
      :key="track.key"
      class="track-lane bg-slate-800/60 border-b border-slate-600/30"
      :style="{ height: `${trackHeight}px` }"
    >
      <div class="track-label text-slate-400 text-xs">
        {{ track.label }}
      </div>

      <div class="track-content">
        <WaveformSubtitleBlock
          v-for="block in blockMap[track.key]"
          :key="`${track.key}-${block.subtitle.start}-${block.subtitle.end}-${block.subtitle.text}`"
          :subtitle="block.subtitle"
          :left-px="block.leftPx"
          :width-px="block.widthPx"
          :is-current="block.isCurrent"
          :marker-color="track.markerColor"
          :track-label="track.label"
          @seek="handleSeek"
        />
      </div>
    </div>

    <div
      v-if="visibleTrackCount > 0"
      class="playhead bg-red-500 w-0.5 absolute z-10"
      :style="{ left: `${playheadLeft}px` }"
      @mousedown="onPlayheadDragStart"
    >
      <div class="playhead-handle"></div>
    </div>
  </div>
</template>

<style scoped>
.overlay-container {
  position: relative;
  overflow: visible;
  cursor: pointer;
}

.overlay-container.is-dragging {
  cursor: col-resize;
}

.track-lane {
  position: relative;
}

.track-lane:last-of-type {
  border-bottom: none;
}

.track-label {
  position: absolute;
  top: 4px;
  left: 8px;
  z-index: 4;
  line-height: 1;
  pointer-events: none;
  user-select: none;
}

.track-content {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.playhead {
  top: 0;
  bottom: 0;
  transform: translateX(-1px);
  cursor: col-resize;
}

.playhead-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -5px;
  width: 11px;
  /* transparent grab area — the 0.5px line is the visible part */
}
</style>
