import { ref } from 'vue'

const dirtyVideoIds = ref<Set<number>>(new Set())

export function markVideoDirty(videoId: number) {
  if (!Number.isFinite(videoId) || videoId <= 0) return
  dirtyVideoIds.value = new Set(dirtyVideoIds.value).add(videoId)
}

export function hasDirtyVideos() {
  return dirtyVideoIds.value.size > 0
}

export function consumeDirtyVideos() {
  const ids = Array.from(dirtyVideoIds.value)
  dirtyVideoIds.value = new Set()
  return ids
}
