import { ref, onMounted, onUnmounted } from 'vue'

const progress = ref(0)
const visible = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

export function useProgress() {
  const start = () => {
    progress.value = 0
    visible.value = true
    if (timer) clearInterval(timer)
    
    timer = setInterval(() => {
      if (progress.value < 90) {
        progress.value += Math.random() * 15
        if (progress.value > 90) progress.value = 90
      }
    }, 200)
  }

  const done = () => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    progress.value = 100
    setTimeout(() => {
      visible.value = false
      progress.value = 0
    }, 300)
  }

  const set = (value: number) => {
    progress.value = Math.min(Math.max(value, 0), 100)
  }

  const trackRouteLoading = () => {
    start()
    
    const observer = new PerformanceObserver((list) => {
      const entries = list.getEntries()
      entries.forEach((entry) => {
        if (entry.name.endsWith('.js') || entry.name.endsWith('.css')) {
          const totalResources = performance.getEntriesByType('resource').length
          const loadedResources = performance.getEntriesByType('resource').filter(
            (e) => e.name.endsWith('.js') || e.name.endsWith('.css')
          ).length
          
          const newProgress = Math.min((loadedResources / totalResources) * 100, 90)
          progress.value = newProgress
        }
      })
    })
    
    observer.observe({ entryTypes: ['resource'] })
    
    setTimeout(() => {
      observer.disconnect()
      done()
    }, 5000)
    
    return () => {
      observer.disconnect()
    }
  }

  return { progress, visible, start, done, set, trackRouteLoading }
}
