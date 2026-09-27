import { ref, watch } from 'vue'

// Library-wide switch: blur every VideoCard thumbnail until the card is hovered.
// Kept across reloads so a page opened in public does not come back unblurred.
const STORAGE_KEY = 'vidgo_blur_thumbnails'

function loadSaved(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

const blurThumbnails = ref(loadSaved())

watch(blurThumbnails, (value) => {
  try {
    localStorage.setItem(STORAGE_KEY, String(value))
  } catch (error) {
    console.error('Failed to persist thumbnail blur preference:', error)
  }
})

export function useThumbnailBlur() {
  return { blurThumbnails }
}
