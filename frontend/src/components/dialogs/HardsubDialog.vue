<!-- 硬字幕提取：让用户在画面上直接框出字幕所在的位置 -->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('hardsubExtract')"
    width="min(900px, 92vw)"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="onClosed"
  >
    <div class="space-y-4">
      <p class="text-sm text-slate-600 dark:text-slate-300">{{ t('hardsubHint') }}</p>
      <p v-if="useServerFrame" data-hardsub-fallback-note class="text-xs text-amber-600 dark:text-amber-400">
        {{ t('hardsubServerFrame') }}
      </p>

      <!-- 画面 + 框选层 -->
      <div
        ref="stageRef"
        class="relative select-none overflow-hidden rounded-lg bg-black"
        data-hardsub-stage
        @pointerdown="onDown"
        @pointermove="onMove"
        @pointerup="onUp"
        @pointerleave="onUp"
      >
        <video
          v-show="!useServerFrame"
          ref="videoRef"
          :src="videoSrc"
          class="block w-full"
          preload="metadata"
          muted
          playsinline
          @loadedmetadata="onLoaded"
          @loadeddata="checkDecode"
        />
        <img
          v-if="useServerFrame"
          :src="frameUrl"
          class="block w-full"
          data-hardsub-server-frame
          alt=""
        />
        <div
          v-if="box"
          class="pointer-events-none absolute border-2 border-emerald-400 bg-emerald-400/15"
          :style="boxStyle"
        />
        <div
          v-if="box"
          class="pointer-events-none absolute left-2 top-2 rounded bg-black/70 px-2 py-1 font-mono text-xs text-emerald-300"
        >
          {{ regionLabel }}
        </div>
      </div>

      <!-- 取帧位置 -->
      <div class="flex items-center gap-3">
        <span class="w-20 shrink-0 text-sm text-slate-600 dark:text-slate-300">{{ t('hardsubSeek') }}</span>
        <el-slider
          v-model="seekPercent"
          :min="0"
          :max="100"
          :step="1"
          class="flex-1"
          @change="applySeek"
        />
        <span class="w-16 shrink-0 text-right font-mono text-xs text-slate-500">{{ seekLabel }}</span>
      </div>

      <div class="flex flex-wrap items-center gap-6">
        <div class="flex items-center gap-2">
          <span class="text-sm text-slate-600 dark:text-slate-300">{{ t('hardsubFps') }}</span>
          <el-radio-group v-model="fps" size="small">
            <el-radio-button :value="4">4</el-radio-button>
            <el-radio-button :value="8">8</el-radio-button>
          </el-radio-group>
          <span class="text-xs text-slate-400">{{ t('hardsubFpsHint') }}</span>
        </div>
        <el-checkbox v-model="keepEn">{{ t('hardsubKeepEn') }}</el-checkbox>
        <el-button size="small" text @click="useDefaultBand">{{ t('hardsubDefaultBand') }}</el-button>
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">{{ t('cancel') }}</el-button>
      <el-button type="primary" :disabled="!box || submitting" data-hardsub-submit @click="submit">
        {{ submitting ? t('saving') : t('hardsubStart') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from '@/composables/useNotification'
import { BACKEND } from '@/composables/ConfigAPI'
import { getCookie } from '@/composables/GetCSRFToken'

const props = defineProps<{
  modelValue: boolean
  videoId: number
  videoName?: string
  videoFile: string
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submitted'): void
}>()

const { t } = useI18n()
const videoRef = ref<HTMLVideoElement | null>(null)
const stageRef = ref<HTMLElement | null>(null)
const fps = ref<4 | 8>(4)
const keepEn = ref(false)
const submitting = ref(false)
const seekPercent = ref(35)
const duration = ref(0)
// Chrome 在 Linux 上解不了 HEVC：不报错、readyState 照样到 4，就是不出帧。
// 库里约六分之一的视频是 HEVC，这时退回服务器取帧，框选逻辑完全不受影响。
const useServerFrame = ref(false)
let decodeTimer: ReturnType<typeof setTimeout> | undefined

// 框选结果一律存成 0-1 的比例，和画面像素尺寸无关
const box = ref<{ x: number; y: number; w: number; h: number } | null>(null)
let dragStart: { x: number; y: number } | null = null

const videoSrc = computed(() => `${BACKEND}/media/video/${encodeURIComponent(props.videoFile)}`)
const seekSeconds = computed(() => Math.floor((duration.value * seekPercent.value) / 100))
const frameUrl = computed(
  () => `${BACKEND}/api/videos/${props.videoId}/frame?t=${seekSeconds.value}&w=960`,
)
const boxStyle = computed(() =>
  box.value
    ? {
        left: `${box.value.x * 100}%`,
        top: `${box.value.y * 100}%`,
        width: `${box.value.w * 100}%`,
        height: `${box.value.h * 100}%`,
      }
    : {},
)
const regionLabel = computed(() =>
  box.value
    ? `x ${box.value.x.toFixed(3)}  y ${box.value.y.toFixed(3)}  w ${box.value.w.toFixed(3)}  h ${box.value.h.toFixed(3)}`
    : '',
)
const seekLabel = computed(() => {
  const s = (duration.value * seekPercent.value) / 100
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
})

function ratio(ev: PointerEvent) {
  const el = stageRef.value
  if (!el) return { x: 0, y: 0 }
  const r = el.getBoundingClientRect()
  return {
    x: Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)),
    y: Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height)),
  }
}

function onDown(ev: PointerEvent) {
  dragStart = ratio(ev)
  box.value = null
  ;(ev.target as HTMLElement).setPointerCapture?.(ev.pointerId)
}

function onMove(ev: PointerEvent) {
  if (!dragStart) return
  const now = ratio(ev)
  box.value = {
    x: Math.min(dragStart.x, now.x),
    y: Math.min(dragStart.y, now.y),
    w: Math.abs(now.x - dragStart.x),
    h: Math.abs(now.y - dragStart.y),
  }
}

function onUp() {
  dragStart = null
  // 拖出来的框太小多半是误点，丢掉
  if (box.value && (box.value.w < 0.02 || box.value.h < 0.01)) box.value = null
}

function onLoaded() {
  duration.value = videoRef.value?.duration || 0
  applySeek()
  // 元数据到手但迟迟解不出帧，就是解码不了，换服务器取帧
  clearTimeout(decodeTimer)
  decodeTimer = setTimeout(checkDecode, 2500)
}

function checkDecode() {
  if (useServerFrame.value) return
  const v = videoRef.value
  if (v && v.readyState >= 2 && v.videoWidth === 0) {
    useServerFrame.value = true
  }
}

function applySeek() {
  const v = videoRef.value
  // 服务器取帧模式下 frameUrl 会跟着 seekPercent 自己变，不用动 video 元素
  if (!useServerFrame.value && v && duration.value) {
    v.currentTime = (duration.value * seekPercent.value) / 100
  }
}

// 常见版式：字幕压在画面下缘。给个起手位置，用户再拖着改
function useDefaultBand() {
  box.value = { x: 0, y: 0.84, w: 1, h: 0.13 }
}

function onClosed() {
  box.value = null
  dragStart = null
  useServerFrame.value = false
  clearTimeout(decodeTimer)
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      seekPercent.value = 35
      box.value = null
    }
  },
)

async function submit() {
  if (!box.value) return
  submitting.value = true
  try {
    const res = await fetch(`${BACKEND}/api/tasks/hardsub/add`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify({
        video_id: props.videoId,
        region: box.value,
        fps: fps.value,
        keep_en: keepEn.value,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`)
    ElMessage.success(t('hardsubQueued'))
    emit('submitted')
    emit('update:modelValue', false)
  } catch (err) {
    ElMessage.error(`${t('hardsubFailed')}: ${err}`)
  } finally {
    submitting.value = false
  }
}
</script>
