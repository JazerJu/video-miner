import { ref } from 'vue'
import type { Video } from '@/types/media'

export function useThumbnail() {
  const showThumbnailDialog = ref(false)
  const currentVideo = ref<Video | null>(null)
  const thumbnailTarget = ref<Video | null>(null)

  function onEditThumbnail(target: Video) {
    console.log('onEditThumbnail called with target:', target)
    currentVideo.value = target
    thumbnailTarget.value = target
    showThumbnailDialog.value = true
  }

  function handleThumbnailUpdated(refreshCallback?: () => void) {
    console.log('handleThumbnailUpdated called')
    // Close the dialog
    showThumbnailDialog.value = false

    // Call refresh callback if provided
    if (refreshCallback) {
      refreshCallback()
    }
  }

  function closeThumbnailDialog() {
    showThumbnailDialog.value = false
    currentVideo.value = null
    thumbnailTarget.value = null
  }

  return {
    showThumbnailDialog,
    currentVideo,
    thumbnailTarget,
    onEditThumbnail,
    handleThumbnailUpdated,
    closeThumbnailDialog,
  }
}
