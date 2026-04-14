<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  duration: number
  pixelsPerSecond: number
  contentWidth: number
  currentTime?: number
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  currentTime: 0,
  height: 28,
})

const intervalOptions = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]

const safePixelsPerSecond = computed(() => Math.max(props.pixelsPerSecond, 1))

function pickInterval(target: number) {
  return (
    intervalOptions.find((interval) => interval >= target) ??
    intervalOptions[intervalOptions.length - 1]
  )
}

const majorInterval = computed(() => {
  const spacingTarget = 96 / safePixelsPerSecond.value
  const densityTarget = props.duration > 0 ? props.duration / 180 : 0
  return pickInterval(Math.max(spacingTarget, densityTarget))
})

const secondaryInterval = computed(() => {
  const majorSpacingPx = majorInterval.value * safePixelsPerSecond.value

  if (majorSpacingPx < 72) {
    return 0
  }

  const interval = Number((majorInterval.value / 2).toFixed(3))

  if (!interval || interval * safePixelsPerSecond.value < 28) {
    return 0
  }

  return interval
})

const tertiaryInterval = computed(() => {
  if (secondaryInterval.value <= 0) return 0

  const secSpacingPx = secondaryInterval.value * safePixelsPerSecond.value
  if (secSpacingPx < 20) return 0

  // Try dividing by 5 for fine granularity (e.g. 5s→1s, 2s→0.4s, 1s→0.2s)
  const by5 = Number((secondaryInterval.value / 5).toFixed(2))
  if (by5 >= 0.05 && by5 * safePixelsPerSecond.value >= 6) {
    return by5
  }

  // Fall back to dividing by 2
  const by2 = Number((secondaryInterval.value / 2).toFixed(2))
  if (by2 >= 0.05 && by2 * safePixelsPerSecond.value >= 6) {
    return by2
  }

  return 0
})

function isMajorTick(time: number) {
  const ratio = time / majorInterval.value
  return Math.abs(ratio - Math.round(ratio)) < 0.001
}

function formatTickLabel(time: number) {
  if (time >= 3600) {
    const hours = Math.floor(time / 3600)
    const minutes = Math.floor((time % 3600) / 60)
    const seconds = Math.floor(time % 60)
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }

  if (time >= 60) {
    const minutes = Math.floor(time / 60)
    const seconds = Math.floor(time % 60)
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  }

  if (majorInterval.value < 1) {
    return `${time.toFixed(1)}s`
  }

  return `0:${String(Math.floor(time)).padStart(2, '0')}`
}

function formatSecondaryLabel(time: number) {
  if (time >= 3600) {
    const hours = Math.floor(time / 3600)
    const minutes = Math.floor((time % 3600) / 60)
    const seconds = Math.floor(time % 60)
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }

  if (time >= 60) {
    const minutes = Math.floor(time / 60)
    const seconds = Math.floor(time % 60)
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  }

  // Sub-minute: show compact form
  if (Number.isInteger(time)) {
    return `${time}`
  }
  return `${time.toFixed(1)}`
}

function formatTertiaryLabel(time: number) {
  if (time >= 60) {
    const minutes = Math.floor(time / 60)
    const seconds = Math.floor(time % 60)
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  }

  // Sub-minute: ultra compact
  if (Number.isInteger(time)) {
    return `${time}`
  }
  return `${time.toFixed(1)}`
}

const ticks = computed(() => {
  if (props.duration <= 0) {
    return []
  }

  const tickMap = new Map<
    string,
    {
      time: number
      left: number
      isMajor: boolean
      isTertiary: boolean
      label: string
      lane: 'upper' | 'lower' | null
    }
  >()

  const buildTickTimes = (interval: number) => {
    const times: number[] = []
    const count = Math.ceil(props.duration / interval)

    for (let index = 0; index <= count; index += 1) {
      const rawTime = Number((index * interval).toFixed(3))

      if (rawTime > props.duration + interval / 2) {
        break
      }

      times.push(Number(Math.min(rawTime, props.duration).toFixed(3)))
    }

    return times
  }

  let labelLaneIndex = 0

  buildTickTimes(majorInterval.value).forEach((time) => {
    const lane = labelLaneIndex % 2 === 0 ? 'upper' : 'lower'
    labelLaneIndex += 1

    tickMap.set(time.toFixed(3), {
      time,
      left: time * safePixelsPerSecond.value,
      isMajor: true,
      isTertiary: false,
      label: formatTickLabel(time),
      lane,
    })
  })

  if (secondaryInterval.value > 0) {
    // Only show secondary labels if spacing is wide enough to avoid overlap (~50px)
    const secSpacingPx = secondaryInterval.value * safePixelsPerSecond.value
    const showSecondaryLabels = secSpacingPx >= 50

    buildTickTimes(secondaryInterval.value).forEach((time) => {
      const key = time.toFixed(3)

      if (tickMap.has(key) || isMajorTick(time)) {
        return
      }

      const lane = showSecondaryLabels
        ? (labelLaneIndex % 2 === 0 ? 'upper' : 'lower')
        : null
      if (showSecondaryLabels) labelLaneIndex += 1

      tickMap.set(key, {
        time,
        left: time * safePixelsPerSecond.value,
        isMajor: false,
        isTertiary: false,
        label: showSecondaryLabels ? formatSecondaryLabel(time) : '',
        lane,
      })
    })
  }

  if (tertiaryInterval.value > 0) {
    const tertiarySpacingPx = tertiaryInterval.value * safePixelsPerSecond.value
    // Show tertiary labels when spacing allows (~36px minimum for a short label)
    const showTertiaryLabels = tertiarySpacingPx >= 36

    buildTickTimes(tertiaryInterval.value).forEach((time) => {
      const key = time.toFixed(3)

      if (tickMap.has(key)) {
        return
      }

      const lane = showTertiaryLabels
        ? (labelLaneIndex % 2 === 0 ? 'upper' : 'lower')
        : null
      if (showTertiaryLabels) labelLaneIndex += 1

      tickMap.set(key, {
        time,
        left: time * safePixelsPerSecond.value,
        isMajor: false,
        isTertiary: true,
        label: showTertiaryLabels ? formatTertiaryLabel(time) : '',
        lane,
      })
    })
  }

  return Array.from(tickMap.values()).sort((left, right) => left.time - right.time)
})

const playheadLeft = computed(() => props.currentTime * safePixelsPerSecond.value)
</script>

<template>
  <div
    class="relative overflow-hidden border-b border-white/[0.04] bg-gradient-to-b from-white/[0.018] via-slate-950/[0.12] to-slate-950/[0.04]"
    :style="{ width: `${contentWidth}px`, height: `${height}px` }"
  >
    <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/[0.04]"></div>

    <div
      v-for="tick in ticks"
      :key="`${tick.time}-${tick.left}`"
      class="absolute inset-y-0"
      :style="{ left: `${tick.left}px` }"
    >
      <span
        v-if="tick.label"
        class="absolute left-1.5 select-none whitespace-nowrap leading-none"
        :class="[
          tick.isMajor
            ? 'text-[9px] font-semibold tracking-[0.18em] text-white/90'
            : tick.isTertiary
              ? 'text-[7px] font-normal tracking-[0.08em] text-white/35'
              : 'text-[8px] font-medium tracking-[0.14em] text-white/50',
          tick.lane === 'lower' ? 'top-[10px]' : 'top-1',
        ]"
      >
        {{ tick.label }}
      </span>

      <div
        class="absolute bottom-0 w-px"
        :class="
          tick.isMajor
            ? 'h-4 bg-white/[0.34]'
            : tick.isTertiary
              ? 'h-1.5 bg-white/[0.12]'
              : 'h-2 bg-white/[0.18]'
        "
      ></div>
    </div>

    <div
      class="pointer-events-none absolute inset-y-0 w-px bg-rose-400/35"
      :style="{ left: `${playheadLeft}px` }"
    ></div>
  </div>
</template>
