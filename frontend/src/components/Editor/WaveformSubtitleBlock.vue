<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import type { Subtitle } from '@/types/subtitle'

const props = withDefaults(
  defineProps<{
    subtitle: Subtitle
    leftPx: number
    widthPx: number
    isCurrent?: boolean
    markerColor?: string
    trackLabel?: string
  }>(),
  {
    isCurrent: false,
    markerColor: '#facc15', // yellow-400 default
    trackLabel: '',
  },
)

const emit = defineEmits<{
  (e: 'seek', time: number): void
}>()

const blockRef = ref<HTMLDivElement>()

const isHovered = ref(false)
const isTruncated = ref(false)

// Fixed-position anchor for the teleported preview
const previewFixed = ref({ top: 0, left: 0, flipBelow: false })

function checkTruncation() {
  if (blockRef.value) {
    isTruncated.value = blockRef.value.scrollWidth > blockRef.value.clientWidth
  }
}

function updatePreviewPosition() {
  if (!blockRef.value) return
  const rect = blockRef.value.getBoundingClientRect()
  const spaceAbove = rect.top
  const flipBelow = spaceAbove < 80 // not enough room above viewport

  previewFixed.value = {
    top: flipBelow ? rect.bottom + 6 : rect.top - 6,
    left: rect.left + rect.width / 2,
    flipBelow,
  }
}

const blockStyle = computed(() => ({
  left: `${props.leftPx}px`,
  width: `${Math.max(props.widthPx, 24)}px`, // minimum 24px
}))

function handleClick() {
  emit('seek', props.subtitle.start)
}

function handleMouseEnter() {
  isHovered.value = true
  checkTruncation()
  nextTick(updatePreviewPosition)
}

function handleMouseLeave() {
  isHovered.value = false
}
</script>

<template>
  <div
    ref="blockRef"
    class="waveform-subtitle-block"
    :class="{ 'is-current': isCurrent }"
    :style="blockStyle"
    @click="handleClick"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
  >
    <!-- Top marker line -->
    <div class="block-marker" :style="{ backgroundColor: markerColor }"></div>
    <!-- Block body with text -->
    <div class="block-body">
      <span class="block-text" :title="isTruncated ? subtitle.text : undefined">
        {{ subtitle.text }}
      </span>
    </div>
  </div>

  <!-- Teleported preview: escapes all ancestor overflow clipping -->
  <Teleport to="body">
    <div
      v-if="isHovered"
      class="block-preview"
      :class="[trackLabel ? 'has-track-label' : '', previewFixed.flipBelow ? 'flip-below' : '']"
      :style="{
        top: `${previewFixed.top}px`,
        left: `${previewFixed.left}px`,
      }"
    >
      <span v-if="trackLabel" class="preview-track-label">{{ trackLabel }}</span>
      <span class="preview-text">{{ subtitle.text }}</span>
    </div>
  </Teleport>
</template>

<style scoped>
.waveform-subtitle-block {
  position: absolute;
  top: 4px;
  height: calc(100% - 8px);
  border-radius: 4px;
  overflow: visible;
  cursor: pointer;
  transition: opacity 0.15s ease, box-shadow 0.15s ease;
  display: flex;
  flex-direction: column;
}

.waveform-subtitle-block:hover {
  opacity: 0.9;
  box-shadow: 0 0 8px rgba(255, 255, 255, 0.15);
  z-index: 2;
}

.waveform-subtitle-block.is-current {
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.4);
  z-index: 3;
}

.block-marker {
  height: 3px;
  width: 100%;
  flex-shrink: 0;
}

/* Preview uses position:fixed via Teleport to body — must use :global to escape scoped */
:global(.block-preview) {
  position: fixed;
  transform: translate(-50%, -100%);
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-width: min(520px, 65vw);
  padding: 8px 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.95);
  box-shadow: 0 8px 24px rgba(2, 6, 23, 0.4);
  backdrop-filter: blur(12px);
  pointer-events: none;
  z-index: 99999;
  transition: opacity 0.1s ease;
}

:global(.block-preview.flip-below) {
  transform: translate(-50%, 0);
}

:global(.preview-track-label) {
  flex-shrink: 0;
  font-size: 10px;
  line-height: 1;
  color: rgba(226, 232, 240, 0.8);
  letter-spacing: 0.08em;
  padding-top: 2px;
}

:global(.preview-text) {
  font-size: 12px;
  line-height: 1.4;
  color: #f1f5f9;
  white-space: normal;
  word-break: break-word;
}

.block-body {
  flex: 1;
  background: rgba(30, 41, 59, 0.85);
  padding: 2px 6px;
  display: flex;
  align-items: center;
  min-width: 0;
}

.block-text {
  font-size: 12px;
  line-height: 1.3;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  user-select: none;
}
</style>
