import { ref } from 'vue'
import { getCSRFToken } from './GetCSRFToken'

export interface LanguageTrack {
  code: string
  name: string
  type: 'original' | 'tts'
  url: string
}

export interface LanguageTracksResponse {
  success: boolean
  data: {
    video_id: number
    video_name: string
    languages: LanguageTrack[]
  }
  error?: string
}

export function useLanguageTracks() {
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const fetchLanguageTracks = async (videoId: number): Promise<LanguageTrack[] | null> => {
    try {
      isLoading.value = true
      error.value = null

      const response = await fetch(`/api/video/${videoId}/languages`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken(),
        },
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data: LanguageTracksResponse = await response.json()

      if (!data.success) {
        throw new Error(data.error || 'Failed to fetch language tracks')
      }

      return data.data.languages
    } catch (err) {
      console.error('[LanguageTracksAPI] Error fetching language tracks:', err)
      error.value = err instanceof Error ? err.message : 'Unknown error'
      return null
    } finally {
      isLoading.value = false
    }
  }

  return {
    fetchLanguageTracks,
    isLoading,
    error,
  }
}