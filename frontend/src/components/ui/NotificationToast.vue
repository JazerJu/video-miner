<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { CheckCircle2, XCircle, AlertCircle, Info } from 'lucide-vue-next'

export interface NotificationProps {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  message: string
  duration?: number
  onClose?: () => void
}

const props = withDefaults(defineProps<NotificationProps>(), {
  duration: 3000,
})

const visible = ref(false)
const closing = ref(false)
const progress = ref(100)
const timer = ref<ReturnType<typeof setTimeout> | null>(null)
const progressTimer = ref<ReturnType<typeof setInterval> | null>(null)

const iconComponent = computed(() => {
  switch (props.type) {
    case 'success':
      return CheckCircle2
    case 'error':
      return XCircle
    case 'warning':
      return AlertCircle
    case 'info':
      return Info
    default:
      return Info
  }
})

const typeStyles = computed(() => {
  switch (props.type) {
    case 'success':
      return {
        border: 'border-emerald-400/30',
        bg: 'bg-emerald-500/10',
        icon: 'text-emerald-400',
        glow: 'shadow-emerald-500/20',
        overlay: 'bg-emerald-500/15',
      }
    case 'error':
      return {
        border: 'border-rose-400/30',
        bg: 'bg-rose-500/10',
        icon: 'text-rose-400',
        glow: 'shadow-rose-500/20',
        overlay: 'bg-rose-500/15',
      }
    case 'warning':
      return {
        border: 'border-amber-400/30',
        bg: 'bg-amber-500/10',
        icon: 'text-amber-400',
        glow: 'shadow-amber-500/20',
        overlay: 'bg-amber-500/15',
      }
    case 'info':
      return {
        border: 'border-blue-400/30',
        bg: 'bg-blue-500/10',
        icon: 'text-blue-400',
        glow: 'shadow-blue-500/20',
        overlay: 'bg-blue-500/15',
      }
    default:
      return {
        border: 'border-slate-400/30',
        bg: 'bg-slate-500/10',
        icon: 'text-slate-400',
        glow: 'shadow-slate-500/20',
        overlay: 'bg-slate-500/15',
      }
  }
})

const close = () => {
  visible.value = false
  closing.value = true
  if (timer.value) {
    clearTimeout(timer.value)
    timer.value = null
  }
  if (progressTimer.value) {
    clearInterval(progressTimer.value)
    progressTimer.value = null
  }
  setTimeout(() => {
    props.onClose?.()
  }, 500)
}

const startTimer = () => {
  if (props.duration > 0) {
    const updateInterval = 16
    const decrement = (100 * updateInterval) / props.duration

    progressTimer.value = setInterval(() => {
      progress.value -= decrement
      if (progress.value <= 0) {
        if (progressTimer.value) {
          clearInterval(progressTimer.value)
        }
      }
    }, updateInterval)

    timer.value = setTimeout(() => {
      close()
    }, props.duration)
  }
}

const pauseTimer = () => {
  if (timer.value) {
    clearTimeout(timer.value)
    timer.value = null
  }
  if (progressTimer.value) {
    clearInterval(progressTimer.value)
    progressTimer.value = null
  }
}

const resumeTimer = () => {
  if (progress.value > 0 && progress.value < 100) {
    const remainingTime = (progress.value / 100) * props.duration
    timer.value = setTimeout(() => {
      close()
    }, remainingTime)

    const updateInterval = 16
    const decrement = (100 * updateInterval) / props.duration
    progressTimer.value = setInterval(() => {
      progress.value -= decrement
      if (progress.value <= 0) {
        if (progressTimer.value) {
          clearInterval(progressTimer.value)
        }
      }
    }, updateInterval)
  }
}

onMounted(() => {
  requestAnimationFrame(() => {
    visible.value = true
    startTimer()
  })
})

onUnmounted(() => {
  if (timer.value) {
    clearTimeout(timer.value)
  }
  if (progressTimer.value) {
    clearInterval(progressTimer.value)
  }
})
</script>

<template>
  <div
    class="notification-item"
    :class="{ 'notification-visible': visible, 'notification-closing': closing }"
    @mouseenter="pauseTimer"
    @mouseleave="resumeTimer"
  >
    <div
      class="notification-content"
      :class="[
        typeStyles.border,
        typeStyles.bg,
        typeStyles.glow,
      ]"
    >
      <!-- Icon -->
      <div
        class="notification-icon"
        :class="typeStyles.icon"
      >
        <component
          :is="iconComponent"
          :size="20"
          class="icon-animated"
        />
      </div>

      <!-- Message -->
      <div class="notification-message">
        {{ message }}
      </div>

      <!-- Close button -->
      <button
        class="notification-close"
        @click="close"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line
            x1="18"
            y1="6"
            x2="6"
            y2="18"
          />
          <line
            x1="6"
            y1="6"
            x2="18"
            y2="18"
          />
        </svg>
      </button>

      <!-- Overlay layer - sweeps from right to left -->
      <div
        v-if="duration > 0 && !closing"
        class="notification-overlay"
        :class="typeStyles.overlay"
        :style="{ width: `${progress}%` }"
      />
    </div>
  </div>
</template>

<style scoped>
.notification-item {
  transform: translateX(120%);
  opacity: 0;
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  margin-bottom: 12px;
}

.notification-visible {
  transform: translateX(0);
  opacity: 1;
}

.notification-item.notification-closing {
  transform: none;
  opacity: 0;
}

.notification-content {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  min-width: 280px;
  max-width: 400px;
  border-radius: 12px;
  border: 1px solid;
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  background: rgba(30, 41, 59, 0.85);
  box-shadow:
    0 8px 32px -4px rgba(0, 0, 0, 0.3),
    0 0 0 1px rgba(255, 255, 255, 0.05) inset;
  position: relative;
  overflow: hidden;
}

.notification-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
}

.icon-animated {
  animation: iconPop 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes iconPop {
  0% {
    transform: scale(0) rotate(-45deg);
    opacity: 0;
  }
  50% {
    transform: scale(1.2) rotate(5deg);
  }
  100% {
    transform: scale(1) rotate(0);
    opacity: 1;
  }
}

.notification-message {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  line-height: 1.5;
  letter-spacing: 0.01em;
}

.notification-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
  padding: 0;
}

.notification-close:hover {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.8);
}

.notification-close:active {
  transform: scale(0.95);
}

.notification-overlay {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  height: 100%;
  transition: width 0.1s linear;
  z-index: 10;
}

.notification-overlay::after {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: rgba(255, 255, 255, 0.3);
}

/* Light mode support */
@media (prefers-color-scheme: light) {
  .notification-content {
    background: rgba(255, 255, 255, 0.9);
    box-shadow:
      0 8px 32px -4px rgba(0, 0, 0, 0.15),
      0 0 0 1px rgba(0, 0, 0, 0.05) inset;
  }

  .notification-message {
    color: rgba(30, 41, 59, 0.9);
  }

  .notification-icon {
    background: rgba(0, 0, 0, 0.05);
  }

  .notification-close {
    color: rgba(0, 0, 0, 0.4);
  }

  .notification-close:hover {
    background: rgba(0, 0, 0, 0.1);
    color: rgba(0, 0, 0, 0.8);
  }

  .notification-progress {
    background: rgba(0, 0, 0, 0.05);
  }
}
</style>
