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

// Extract filename from video URL - returns full filename like "abc123.mp4"
export function extractVideoUrlFilename(videoUrl: string): string | null {
  const urlPath = videoUrl.split('/').pop()
  if (!urlPath) return null
  return urlPath
}

// Fetch waveform peak data using filename (video or audio)
export async function fetchWaveformPeaksByFilename(filename: string): Promise<WaveformPeakData | null> {
  try {
    const response = await fetch(`${BACKEND}/api/waveform/${encodeURIComponent(filename)}`, {
      credentials: 'include',
    })

    if (!response.ok) {
      if (response.status === 404) {
        console.log('Waveform peaks not found for:', filename)
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

// Trigger audio extraction from video
export async function extractAudioFromVideo(videoId: number): Promise<{ success: boolean; audioFilename?: string; error?: string }> {
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

    const result = await response.json()

    if (response.ok && result.success) {
      // Extract audio filename from audio_path
      const audioPath = result.audio_path as string
      const audioFilename = audioPath.split('/').pop()
      return {
        success: true,
        audioFilename: audioFilename || `${videoId}.m4a`,
      }
    } else {
      return {
        success: false,
        error: result.error || 'Failed to extract audio',
      }
    }
  } catch (error) {
    console.error('Error extracting audio:', error)
    return {
      success: false,
      error: 'Network error during audio extraction',
    }
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

// Composable for managing waveform peaks with audio extraction
export function useWaveformPeaks(videoId: number, videoUrl: string) {
  const isLoading = ref(false)
  const waveformPeaks = ref<WaveformPeakData | null>(null)
  const loadingMessage = ref('Loading waveform data...')
  const checkInterval = ref<number | null>(null)

  const videoFilename = ref<string | null>(null)
  const audioFilename = ref<string | null>(null)

  function initializeFilenames(): void {
    videoFilename.value = extractVideoUrlFilename(videoUrl)
    if (!videoFilename.value) {
      console.warn('Could not extract filename from video URL:', videoUrl)
    }
  }

  async function tryFetchPeaks(filename: string): Promise<boolean> {
    const peaks = await fetchWaveformPeaksByFilename(filename)
    if (peaks) {
      waveformPeaks.value = peaks
      console.log('Successfully loaded waveform peaks:', filename)
      return true
    }
    return false
  }

  async function loadWaveformPeaks(): Promise<void> {
    try {
      isLoading.value = true
      loadingMessage.value = 'Loading waveform data...'

      if (!videoFilename.value) {
        loadingMessage.value = 'Invalid video URL'
        isLoading.value = false
        return
      }

      // Step 1: Try video file peaks directly (some videos have audio tracks)
      let peaksFound = await tryFetchPeaks(videoFilename.value)
      if (peaksFound) {
        isLoading.value = false
        return
      }

      // Step 2: Extract audio from video
      loadingMessage.value = 'Extracting audio...'
      const extractionResult = await extractAudioFromVideo(videoId)

      if (!extractionResult.success) {
        console.error('Audio extraction failed:', extractionResult.error)
        loadingMessage.value = extractionResult.error || 'Failed to extract audio'
        isLoading.value = false
        return
      }

      audioFilename.value = extractionResult.audioFilename || null

      if (!audioFilename.value) {
        loadingMessage.value = 'Audio extraction returned no filename'
        isLoading.value = false
        return
      }

      // Step 3: Try to fetch peaks for the extracted audio
      loadingMessage.value = 'Generating waveform from audio...'
      peaksFound = await tryFetchPeaks(audioFilename.value)

      if (peaksFound) {
        isLoading.value = false
        return
      }

      // Step 4: Start polling if peaks still not available
      loadingMessage.value = 'Waiting for waveform generation...'
      startPolling()
    } catch (error) {
      console.error('Error in loadWaveformPeaks:', error)
      loadingMessage.value = 'Error loading waveform data'
      isLoading.value = false
    }
  }

  async function pollForPeaks(): Promise<void> {
    // Try audio file first, then video file as fallback
    const filenameToTry = audioFilename.value || videoFilename.value
    if (!filenameToTry) return

    const peaksFound = await tryFetchPeaks(filenameToTry)

    if (peaksFound) {
      isLoading.value = false
      stopPolling()
      loadingMessage.value = 'Waveform data loaded successfully'
    }
  }

  function startPolling(): void {
    if (checkInterval.value) return

    console.log('Polling for waveform peaks every 5 seconds...')
    checkInterval.value = window.setInterval(pollForPeaks, 5000)
  }

  function stopPolling(): void {
    if (checkInterval.value) {
      clearInterval(checkInterval.value)
      checkInterval.value = null
    }
  }

  async function initialize(): Promise<void> {
    initializeFilenames()
    await loadWaveformPeaks()
  }

  function cleanup(): void {
    stopPolling()
  }

  return {
    isLoading,
    waveformPeaks,
    loadingMessage,
    initialize,
    cleanup,
  }
}
