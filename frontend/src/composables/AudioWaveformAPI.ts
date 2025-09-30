import { ref, computed } from 'vue'

export interface WaveformPeakData {
  version: string
  audio_file: string
  duration: number
  samples_per_second: number
  length: number
  peaks: number[]
}

export interface AudioDetectionResult {
  success: boolean
  has_audio: boolean
  is_audio_file: boolean
  audio_filename?: string
  audio_path?: string
  audio_size?: number
  audio_format?: string
  message?: string
}

import { BACKEND } from '@/composables/ConfigAPI'
import { getCSRFToken } from '@/composables/GetCSRFToken'

// Check if audio file exists for the video (using video ID)
export async function checkAudioFile(videoId: number): Promise<AudioDetectionResult> {
  try {
    const response = await fetch(`${BACKEND}/api/videos/${videoId}/has_audio`, {
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const result = await response.json()
    return result as AudioDetectionResult
  } catch (error) {
    console.error('Failed to check audio file:', error)
    return {
      success: false,
      has_audio: false,
      is_audio_file: false,
      message: 'Failed to check audio file availability',
    }
  }
}

// Extract MD5 hash from video URL - assumes URL format like "/media/video/92a3fcc6ac30d6616e09d81dec029757.mp4"
export function extractVideoUrlMd5(videoUrl: string): string | null {
  const urlPath = videoUrl.split('/').pop() // Get filename part
  if (!urlPath) return null

  const filename = urlPath.split('.')[0] // Remove extension

  return filename
}

// Fetch waveform peak data using MD5 hash from video URL
export async function fetchWaveformPeaksByMd5(md5Hash: string): Promise<WaveformPeakData | null> {
  try {
    const response = await fetch(`${BACKEND}/api/waveform/${md5Hash}`, {
      credentials: 'include',
    })

    if (!response.ok) {
      if (response.status === 404) {
        console.log('Waveform peaks not found for MD5:', md5Hash)
        return null
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const peaksData = await response.json()
    return peaksData as WaveformPeakData
  } catch (error) {
    console.error('Failed to fetch waveform peaks by MD5:', error)
    return null
  }
}

// Generate waveform peaks for a video
export async function generateWaveformPeaks(videoId: number): Promise<boolean> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/${videoId}/generate_waveform_peaks`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
    })

    if (response.ok) {
      console.log('Waveform peak generation started for video:', videoId)
      return true
    } else {
      console.error('Failed to start waveform generation:', response.status)
      return false
    }
  } catch (error) {
    console.error('Error generating waveform peaks:', error)
    return false
  }
}

// Fetch waveform peak data (legacy function for backward compatibility)
export async function fetchWaveformPeaks(audioFilename: string): Promise<WaveformPeakData | null> {
  try {
    const response = await fetch(`${BACKEND}/api/waveform/${encodeURIComponent(audioFilename)}`, {
      credentials: 'include',
    })

    if (!response.ok) {
      if (response.status === 404) {
        console.log('Waveform data not found, will be generated')
        return null
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const peaksData = await response.json()
    return peaksData as WaveformPeakData
  } catch (error) {
    console.error('Failed to fetch waveform peaks:', error)
    return null
  }
}

// Trigger audio extraction from video (using video ID)
export async function triggerAudioExtraction(videoId: number): Promise<boolean> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/${videoId}/extract_audio`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
    })

    return response.ok
  } catch (error) {
    console.error('Failed to trigger audio extraction:', error)
    return false
  }
}

// Composable for managing waveform peaks with the specified logic
export function useWaveformPeaks(videoId: number, videoUrl: string) {
  const isLoading = ref(false)
  const waveformPeaks = ref<WaveformPeakData | null>(null)
  const loadingMessage = ref('Loading waveform data...')
  const checkInterval = ref<number | null>(null)

  // Extract MD5 from video URL for peaks fetching
  const md5Hash = ref<string | null>(null)

  // Initialize MD5 hash from video URL
  function initializeMd5(): void {
    md5Hash.value = extractVideoUrlMd5(videoUrl)
    if (!md5Hash.value) {
      console.warn('Could not extract MD5 hash from video URL:', videoUrl)
    }
  }

  // Try to fetch peaks using MD5 hash (path 1)
  async function tryFetchPeaks(): Promise<boolean> {
    if (!md5Hash.value) {
      console.error('No MD5 hash available for peaks fetching')
      return false
    }

    const peaks = await fetchWaveformPeaksByMd5(md5Hash.value)
    if (peaks) {
      waveformPeaks.value = peaks
      console.log('Successfully loaded waveform peaks from cache')
      return true
    }

    return false
  }

  // Main loading logic
  async function loadWaveformPeaks(): Promise<void> {
    try {
      isLoading.value = true
      loadingMessage.value = 'Loading waveform data...'

      // Step 1: Try to fetch existing peaks
      const peaksFound = await tryFetchPeaks()

      if (peaksFound) {
        isLoading.value = false
        stopPolling()
        return
      }

      // Step 2: If no peaks found, trigger generation
      loadingMessage.value = 'Generating waveform data...'
      const generationStarted = await generateWaveformPeaks(videoId)

      if (generationStarted) {
        // Step 3: Start polling every 10 seconds
        startPolling()
      } else {
        isLoading.value = false
        loadingMessage.value = 'Failed to start waveform generation'
      }
    } catch (error) {
      console.error('Error in loadWaveformPeaks:', error)
      isLoading.value = false
      loadingMessage.value = 'Error loading waveform data'
    }
  }

  // Polling function - called every 10 seconds
  async function pollForPeaks(): Promise<void> {
    const peaksFound = await tryFetchPeaks()

    if (peaksFound) {
      isLoading.value = false
      stopPolling()
      loadingMessage.value = 'Waveform data loaded successfully'
    }
  }

  // Start polling for peaks availability
  function startPolling(): void {
    if (checkInterval.value) return // Already polling

    console.log('Starting to poll for waveform peaks every 10 seconds...')
    checkInterval.value = window.setInterval(pollForPeaks, 10000) // Poll every 10 seconds
  }

  // Stop polling
  function stopPolling(): void {
    if (checkInterval.value) {
      console.log('Stopping waveform peaks polling')
      clearInterval(checkInterval.value)
      checkInterval.value = null
    }
  }

  // Initialize and start the loading process
  async function initialize(): Promise<void> {
    initializeMd5()
    await loadWaveformPeaks()
  }

  // Cleanup
  function cleanup(): void {
    stopPolling()
  }

  return {
    isLoading,
    waveformPeaks,
    loadingMessage,
    initialize,
    cleanup,
    loadWaveformPeaks,
    startPolling,
    stopPolling,
  }
}
