<!-- 视频播放器核心组件 -->
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import videojs from 'video.js'
import type Player from 'video.js/dist/types/player'
import { ChapterAPI } from '@/composables/ChapterAPI'
import { Settings } from 'lucide-vue-next'
import { useSubtitleStyle } from '@/composables/SubtitleStyle'

const props = defineProps<{
  src: string
  blobUrls?: (string | undefined)[] // [ zhUrl?, bothUrl?, enUrl? ] Also can be null.
  videoId?: number // Add video ID for chapter loading
}>()
const emit = defineEmits<{ 
  (e: 'time-update', t: number): void
  (e: 'autoplay-next'): void
  (e: 'autoplay-settings-changed', enabled: boolean): void
  (e: 'fullscreen-change', isFullscreen: boolean): void
}>()

// 使用字幕样式composable
const { subtitleSettings, loadSubtitleSettings, injectGlobalSubtitleStyles, cleanup: cleanupSubtitleStyles } = useSubtitleStyle()

const TRACK_PREFIX = 'dynamic-vtt-'

// Function to detect media MIME type from URL (supports both video and audio)
function getMediaMimeType(url: string): string {
  const extension = url.split('.').pop()?.toLowerCase()

  switch (extension) {
    // Video formats
    case 'mp4':
      return 'video/mp4'
    case 'webm':
      return 'video/webm'
    case 'mkv':
      return 'video/x-matroska'
    case 'avi':
      return 'video/x-msvideo'
    case 'mov':
      return 'video/quicktime'
    case 'ogv':
      return 'video/ogg'
    // Audio formats
    case 'm4a':
      return 'audio/mp4'
    case 'mp3':
      return 'audio/mpeg'
    case 'wav':
      return 'audio/wav'
    case 'ogg':
      return 'audio/ogg'
    case 'flac':
      return 'audio/flac'
    case 'aac':
      return 'audio/aac'
    default:
      // For AV1 codec, we need to check the container format
      // AV1 can be in MP4, WebM, or other containers
      // If we can't determine, try MP4 first as it's most common for AV1
      return 'video/mp4'
  }
}

// Function to detect if browser supports AV1
function supportsAV1(): boolean {
  const video = document.createElement('video')
  // Check for both 'probably' and 'maybe' support
  const mp4Support = video.canPlayType('video/mp4; codecs="av01.0.08M.08"')
  const webmSupport = video.canPlayType('video/webm; codecs="av01.0.08M.08"')
  
  return (
    mp4Support === 'probably' || mp4Support === 'maybe' ||
    webmSupport === 'probably' || webmSupport === 'maybe'
  )
}

// Function to detect if browser supports HEVC/H.265
function supportsHEVC(): boolean {
  const video = document.createElement('video')
  // Check for HEVC support in MP4 containers
  const hevcSupport = video.canPlayType('video/mp4; codecs="hvc1.1.6.L93.B0"')
  const hevcAltSupport = video.canPlayType('video/mp4; codecs="hev1.1.6.L93.B0"')
  
  console.log('[VideoPlayer] HEVC Support Check:', {
    hvc1: hevcSupport,
    hev1: hevcAltSupport
  })
  
  return (
    hevcSupport === 'probably' || hevcSupport === 'maybe' ||
    hevcAltSupport === 'probably' || hevcAltSupport === 'maybe'
  )
}

// Function to get multiple source options for better codec support
function getVideoSources(url: string): Array<{ src: string; type: string }> {
  const baseMimeType = getMediaMimeType(url)
  const sources = []
  const av1Supported = supportsAV1()
  const hevcSupported = supportsHEVC()

  console.log(`[VideoPlayer] Codec Support - AV1: ${av1Supported}, HEVC: ${hevcSupported}`)
  console.log(`[VideoPlayer] File MIME type: ${baseMimeType}`)

  // Always try the file as-is first (let the browser decide the best codec)
  sources.push({ src: url, type: baseMimeType })

  if (baseMimeType === 'video/mp4') {
    // For MP4 containers, try different codecs based on browser support
    
    // Try HEVC first if supported (since the problematic video is HEVC)
    if (hevcSupported) {
      sources.push({ src: url, type: 'video/mp4; codecs="hvc1.1.6.L93.B0"' })
      sources.push({ src: url, type: 'video/mp4; codecs="hev1.1.6.L93.B0"' })
      // Additional HEVC profiles
      sources.push({ src: url, type: 'video/mp4; codecs="hvc1.1.6.L120.B0"' })
      sources.push({ src: url, type: 'video/mp4; codecs="hvc1.2.4.L120.B0"' })
    }
    
    // Try AV1 if supported
    if (av1Supported) {
      sources.push({ src: url, type: 'video/mp4; codecs="av01.0.08M.08"' })
      sources.push({ src: url, type: 'video/mp4; codecs="av01.0.05M.08"' })
    }
    
    // H.264 fallback (most widely supported)
    sources.push({ src: url, type: 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"' })
    sources.push({ src: url, type: 'video/mp4; codecs="avc1.4D4015, mp4a.40.2"' }) // Main Profile
    sources.push({ src: url, type: 'video/mp4; codecs="avc1.640015, mp4a.40.2"' }) // High Profile
    
  } else if (baseMimeType === 'video/webm') {
    // For WebM containers
    if (av1Supported) {
      sources.push({ src: url, type: 'video/webm; codecs="av01.0.08M.08"' })
      sources.push({ src: url, type: 'video/webm; codecs="av01.0.05M.08"' })
    }
    // VP9 and VP8 fallbacks
    sources.push({ src: url, type: 'video/webm; codecs="vp9"' })
    sources.push({ src: url, type: 'video/webm; codecs="vp8"' })
  } else if (baseMimeType === 'video/x-matroska') {
    // For MKV containers - specific handling for Matroska format
    if (hevcSupported) {
      // HEVC (H.265) variants for MKV with different profiles and levels
      sources.push({ src: url, type: 'video/x-matroska; codecs="hvc1.2.4.L150.B0"' }) // Main10 Profile, Level 5.0
      sources.push({ src: url, type: 'video/x-matroska; codecs="hev1.2.4.L150.B0"' }) // Alternative HEVC format
      sources.push({ src: url, type: 'video/x-matroska; codecs="hvc1.1.6.L120.B0"' }) // Main Profile, Level 4.0
      sources.push({ src: url, type: 'video/x-matroska; codecs="hev1.1.6.L120.B0"' }) // Alternative format
    }
    if (av1Supported) {
      sources.push({ src: url, type: 'video/x-matroska; codecs="av01.0.08M.08"' })
    }
    // H.264 in MKV container
    sources.push({ src: url, type: 'video/x-matroska; codecs="avc1.64001F"' }) // High Profile
    sources.push({ src: url, type: 'video/x-matroska; codecs="avc1.4D401F"' }) // Main Profile
    // VP9 and VP8 fallbacks for MKV
    sources.push({ src: url, type: 'video/x-matroska; codecs="vp9"' })
  } else {
    // For other container formats
    if (av1Supported) {
      sources.push({ src: url, type: `${baseMimeType}; codecs="av01.0.08M.08"` })
    }
    if (hevcSupported) {
      sources.push({ src: url, type: `${baseMimeType}; codecs="hvc1.1.6.L93.B0"` })
    }
  }

  // Add a basic fallback without codec specification
  sources.push({ src: url, type: 'video/mp4' })

  console.log('[VideoPlayer] Generated sources:', sources)
  return sources
}

// Dynamic descriptors are now created in updateSubtitleTracks based on available content

// Chapter management
interface Chapter {
  id: string
  title: string
  startTime: number
  endTime?: number
  thumbnail?: string
}

const chapters = ref<Chapter[]>([])
const currentTime = ref(0)
const currentChapter = ref<Chapter | null>(null)

// Autoplay and background play state management
const isAutoPlayEnabled = ref(false)
const isBackgroundPlayEnabled = ref(false)

// Hotkey and hint system
const currentSubtitleTrack = ref(0)
const hotkeyHintVisible = ref(false)
const hotkeyHintText = ref('')

let player: Player | null = null
const videoEl = ref<HTMLVideoElement | null>(null) // <- THE ONLY REF

defineExpose({
  seek: (t: number) => player?.currentTime(t),
  pause: () => player?.pause(),
  play: () => player?.play(),
  currentTime: getCurrentTime,
})

function updateSubtitleTracks(player: Player | null, urls: (string | undefined)[] | undefined) {
  if (!player) return

  const list = player.remoteTextTracks()
  for (let i = (list as any).length - 1; i >= 0; i--) {
    const track = (list as any)[i] as videojs.TextTrack & { id?: string }
    if (track.id?.startsWith(TRACK_PREFIX)) {
      player.removeRemoteTextTrack(track)
    }
  }

  if (!urls) return
  
  // Create dynamic descriptors based on available URLs and their actual content
  const dynamicDescriptors: Array<{ key: string, label: string, srclang: string, index: number }> = []
  
  // blobUrls structure: [primaryLang, foreignLang, both]
  // We need to determine which languages these actually contain
  if (urls[0]) {
    // Primary language subtitle is available
    dynamicDescriptors.push({
      key: 'Primary',
      label: '原文', // Will show the primary language
      srclang: 'primary',
      index: 0
    })
  }
  
  if (urls[1]) {
    // Foreign language subtitle is available  
    dynamicDescriptors.push({
      key: 'Translation',
      label: '译文', // Will show the translation language
      srclang: 'translation', 
      index: 1
    })
  }
  
  if (urls[2] && urls[0] && urls[1]) {
    // Both languages available - only show if both primary and translation exist
    dynamicDescriptors.push({
      key: 'Both',
      label: '双语', // Bilingual
      srclang: 'both',
      index: 2
    })
  }

  // Add tracks for available subtitles
  dynamicDescriptors.forEach(({ key, label, srclang, index }, i) => {
    const src = urls[index]
    if (!src) return
    
    player.addRemoteTextTrack({
      id: `${TRACK_PREFIX}${key}`,
      kind: 'subtitles',
      label, // 菜单上显示的文字
      language: srclang, // video.js language
      src,
      default: i === 0, // 第一个轨道设为默认
    })

    // Add a listener to detect when this track becomes active and mark the display
    // We need to use a different approach since we can't reliably access the track object
    setTimeout(() => {
      const textTracks = player.textTracks()
      // Convert TextTrackList to array and find the track we just added
      const trackArray = Array.from(textTracks as any) as any[]
      const targetTrack = trackArray.find((track: any) => 
        track.language === srclang && track.kind === 'subtitles'
      )
      
      if (targetTrack) {
        targetTrack.addEventListener('cuechange', () => {
          // Find all text track display containers
          const textTrackDisplays = player.el().querySelectorAll('.vjs-text-track-display')
          textTrackDisplays.forEach((display: Element) => {
            const displayElement = display as HTMLElement
            // Check if this display has active cues from our track
            if (targetTrack.activeCues && targetTrack.activeCues.length > 0) {
              // Mark the display with the subtitle language
              displayElement.setAttribute('data-subtitle-lang', srclang)
            } else {
              // Remove the attribute if no active cues
              displayElement.removeAttribute('data-subtitle-lang')
            }
          })
        })
      }
    }, 100) // Small delay to ensure track is added
  })
}

// Hotkey functionality
function setupHotkeys() {
  const handleKeydown = (e: KeyboardEvent) => {
    // Only handle hotkeys if no input elements are focused and no modals/dropdowns are open
    const activeElement = document.activeElement
    const isInputFocused = activeElement instanceof HTMLInputElement || 
                          activeElement instanceof HTMLTextAreaElement ||
                          (activeElement as any)?.contentEditable === 'true'
    
    const isDropdownOpen = document.querySelector('.speed-dropdown[style*="display: block"]') ||
                          document.querySelector('.chapter-dropdown[style*="display: block"]')
    
    if (isInputFocused || isDropdownOpen || !player) return

    switch (e.key) {
      case ' ':
        e.preventDefault()
        togglePlayPause()
        showHotkeyHint(player.paused() ? 'Space - Paused' : 'Space - Playing')
        break
      case 'ArrowLeft':
        e.preventDefault()
        seekBySeconds(-5)
        showHotkeyHint('← -5s')
        break
      case 'ArrowRight':
        e.preventDefault()
        seekBySeconds(5)
        showHotkeyHint('→ +5s')
        break
      case 'f':
      case 'F':
        // Only handle F key for fullscreen if Ctrl is not pressed
        // This allows Ctrl+F to pass through for subtitle search
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault()
          toggleFullscreen()
          showHotkeyHint(player.isFullscreen() ? 'F - Fullscreen' : 'F - Windowed')
        }
        break
      case 'c':
      case 'C':
        // Only handle C key for subtitle cycling if Ctrl is not pressed
        // This allows Ctrl+C to pass through for copy functionality
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault()
          cycleSubtitles()
        }
        break
    }
  }

  document.addEventListener('keydown', handleKeydown)
  
  // Return cleanup function
  return () => {
    document.removeEventListener('keydown', handleKeydown)
  }
}

function seekBySeconds(seconds: number) {
  if (!player) return
  const currentTime = player.currentTime() || 0
  const newTime = Math.max(0, Math.min(currentTime + seconds, player.duration() || 0))
  player.currentTime(newTime)
}

function toggleFullscreen() {
  if (!player) return
  if (player.isFullscreen()) {
    player.exitFullscreen()
  } else {
    player.requestFullscreen()
  }
}

function togglePlayPause() {
  if (!player) return
  if (player.paused()) {
    player.play()
  } else {
    player.pause()
  }
}

function cycleSubtitles() {
  if (!player) return
  
  const textTracks = player.textTracks()
  const availableTracks: any[] = []
  
  // Find all subtitle tracks - convert TextTrackList to array
  const trackArray = Array.from(textTracks as any) as any[]
  for (const track of trackArray) {
    if ((track as any).kind === 'subtitles') {
      availableTracks.push(track)
    }
  }
  
  if (availableTracks.length === 0) {
    showHotkeyHint('C - No subtitles available')
    return
  }
  
  // Turn off all tracks first
  for (const track of trackArray) {
    if ((track as any).kind === 'subtitles') {
      (track as any).mode = 'hidden'
    }
  }
  
  // Cycle to next track or turn off if at the end
  const totalTracks = availableTracks.length + 1 // +1 for "off" state
  currentSubtitleTrack.value = (currentSubtitleTrack.value + 1) % totalTracks
  
  if (currentSubtitleTrack.value === 0) {
    // "Off" state - all subtitles hidden
    showHotkeyHint('C - Subtitles: Off')
  } else {
    // Enable specific track
    const trackIndex = currentSubtitleTrack.value - 1
    const track = availableTracks[trackIndex]
    track.mode = 'showing'
    showHotkeyHint(`C - ${track.label}`)
  }
}

function showHotkeyHint(text: string) {
  hotkeyHintText.value = text
  hotkeyHintVisible.value = true
  
  // Hide hint after 2 seconds
  setTimeout(() => {
    hotkeyHintVisible.value = false
  }, 2000)
}

function showMediaError(message: string) {
  // Create error overlay
  const errorOverlay = document.createElement('div')
  errorOverlay.style.cssText = `
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    color: white;
    font-size: 16px;
    text-align: center;
    padding: 20px;
    box-sizing: border-box;
  `
  
  const errorMessage = document.createElement('div')
  errorMessage.innerHTML = `
    <div style="background: rgba(220, 53, 69, 0.9); padding: 20px; border-radius: 8px; max-width: 400px;">
      <div style="font-size: 18px; margin-bottom: 10px;">⚠️ 播放错误</div>
      <div style="margin-bottom: 15px;">${message}</div>
      <div style="font-size: 14px; color: rgba(255,255,255,0.8);">
        建议尝试使用其他浏览器或转换视频格式为MP4
      </div>
    </div>
  `
  
  errorOverlay.appendChild(errorMessage)
  
  // Add to video container
  const videoContainer = player?.el()?.parentElement
  if (videoContainer) {
    videoContainer.style.position = 'relative'
    videoContainer.appendChild(errorOverlay)
    
    // Remove error after 10 seconds
    setTimeout(() => {
      if (errorOverlay.parentNode) {
        errorOverlay.parentNode.removeChild(errorOverlay)
      }
    }, 10000)
  }
}
// Background play functionality
function setupBackgroundPlay() {
  if (!player || !('mediaSession' in navigator)) {
    console.warn('[VideoPlayer] Media Session API not supported for background play')
    return
  }

  // Setup Media Session API for background play
  const updateMediaSession = () => {
    if (!isBackgroundPlayEnabled.value) return

    const videoElement = player?.el()?.querySelector('video') as HTMLVideoElement
    if (!videoElement) return

    try {
      // Set media metadata
      navigator.mediaSession.metadata = new MediaMetadata({
        title: props.videoId ? `Video ${props.videoId}` : 'Video Player',
        artist: 'VidGo',
        artwork: [
          { 
            src: '/favicon.ico', 
            sizes: '96x96', 
            type: 'image/x-icon' 
          }
        ]
      })

      // Set action handlers
      navigator.mediaSession.setActionHandler('play', () => {
        console.log('[BackgroundPlay] Media Session play action')
        player?.play()
      })

      navigator.mediaSession.setActionHandler('pause', () => {
        console.log('[BackgroundPlay] Media Session pause action')
        player?.pause()
      })

      navigator.mediaSession.setActionHandler('seekbackward', () => {
        console.log('[BackgroundPlay] Media Session seek backward action')
        seekBySeconds(-10)
      })

      navigator.mediaSession.setActionHandler('seekforward', () => {
        console.log('[BackgroundPlay] Media Session seek forward action')
        seekBySeconds(10)
      })

      // Update playback state
      navigator.mediaSession.playbackState = player?.paused() ? 'paused' : 'playing'

      console.log('[BackgroundPlay] Media Session configured for background play')
    } catch (error) {
      console.error('[BackgroundPlay] Failed to setup Media Session:', error)
    }
  }

  // Setup Wake Lock API for preventing screen sleep
  let wakeLock: any = null
  
  const requestWakeLock = async () => {
    if (!isBackgroundPlayEnabled.value || !('wakeLock' in navigator)) return

    try {
      wakeLock = await (navigator as any).wakeLock.request('screen')
      console.log('[BackgroundPlay] Screen wake lock acquired')
      
      wakeLock.addEventListener('release', () => {
        console.log('[BackgroundPlay] Screen wake lock released')
      })
    } catch (error) {
      console.error('[BackgroundPlay] Wake lock failed:', error)
    }
  }

  const releaseWakeLock = () => {
    if (wakeLock) {
      wakeLock.release()
      wakeLock = null
      console.log('[BackgroundPlay] Screen wake lock released manually')
    }
  }

  // Listen to player events for background play
  player.on('play', () => {
    if (isBackgroundPlayEnabled.value) {
      updateMediaSession()
      requestWakeLock()
      
      // Set video element attributes for better iOS Safari support
      const videoElement = player?.el()?.querySelector('video') as HTMLVideoElement
      if (videoElement) {
        videoElement.setAttribute('playsinline', 'true')
        videoElement.setAttribute('webkit-playsinline', 'true')
        videoElement.muted = false // Ensure audio is enabled for background play
      }
    }
  })

  player.on('pause', () => {
    if (isBackgroundPlayEnabled.value && navigator.mediaSession) {
      navigator.mediaSession.playbackState = 'paused'
    }
    releaseWakeLock()
  })

  player.on('timeupdate', () => {
    if (isBackgroundPlayEnabled.value && navigator.mediaSession && 'setPositionState' in navigator.mediaSession) {
      try {
        navigator.mediaSession.setPositionState({
          duration: player?.duration() || 0,
          playbackRate: player?.playbackRate() || 1,
          position: player?.currentTime() || 0
        })
      } catch (error) {
        // Ignore position state errors
      }
    }
  })

  // Handle visibility change for background play
  document.addEventListener('visibilitychange', () => {
    if (isBackgroundPlayEnabled.value) {
      if (document.hidden) {
        console.log('[BackgroundPlay] Page hidden, maintaining playback')
        // Keep video playing in background
      } else {
        console.log('[BackgroundPlay] Page visible, updating media session')
        updateMediaSession()
      }
    }
  })
}

/* ---------- mount ---------- */
let hotkeyCleanup: (() => void) | null = null

onMounted(async () => {
  if (!videoEl.value) return // safety

  // 加载字幕样式配置
  await loadSubtitleSettings()

  // Register custom components
  createEditableTimeDisplay()
  createCameraSnapshotControl()
  createVideoSettingsControl()
  createVideoSpeedControl()
  createPlayModeToggleControl()
  createChapterDisplay()

  // Setup hotkeys
  hotkeyCleanup = setupHotkeys()

  player = videojs(videoEl.value!, {
    controls: true,
    preload: 'metadata',
    responsive: true,
    language: 'zh-CN',
    fill: true, // another option is fluid:true, It will let videojs to define its css width and height.
    // Enable experimental features and improved codec handling
    experimentalSvgIcons: true,
    html5: {
      // Force HTML5 native video element handling for better codec support
      nativeAudioTracks: false,
      nativeVideoTracks: false,
      // Override MIME type validation to be more permissive
      overrideNative: true,
    },
    // Add crossorigin to prevent canvas taint
    crossorigin: 'anonymous',
    // Add debug logging for source selection
    debug: true,
    controlBar: {
      children: [
        'playToggle',
        'EditableCurrentTimeDisplay',
        'timeDivider',
        'durationDisplay',
        'progressControl',
        'skipBackward',
        'skipForward',
        'ChapterDisplay',
        'liveDisplay',
        'seekToLive',
        'remainingTimeDisplay',
        'customControlSpacer',
        'playbackRateMenuButton',
        'descriptionsButton',
        'subsCapsButton', // 保留字幕按钮，但会禁用其样式设置功能
        'CameraSnapshotControl',
        'VideoSpeedControl',
        'PlayModeToggleControl',
        'VideoSettingsControl',
        'audioTrackButton',
        'ShareButton',
        'hlsQualitySelector',
        'QualitySelector',
        'volumePanel',
        'pictureInPictureToggle',
        'fullscreenToggle',
      ],
      skipButtons: {
        forward: 5,
        backward: 5,
      },
      volumePanel: {
        inline: false,
        vertical: true,
      },
    },
  })

  // Init source + tracks with multiple codec support
  const sources = getVideoSources(props.src)
  player.src(sources)

  // Add error handling for source loading
  let errorRetryCount = 0
  const maxRetries = 3
  
  player.on('error', () => {
    const playerError = player?.error()
    if (playerError) {
      console.error('[VideoPlayer] Video.js error:', {
        code: playerError.code,
        message: playerError.message,
        originalError: playerError,
        retryCount: errorRetryCount
      })
      
      // Try progressive fallback strategies for unsupported media
      if (playerError.code === 4 && errorRetryCount < maxRetries) { // MEDIA_ERR_SRC_NOT_SUPPORTED
        errorRetryCount++
        console.log(`[VideoPlayer] Attempting source recovery ${errorRetryCount}/${maxRetries}`)
        
        const basicMimeType = getMediaMimeType(props.src)
        let fallbackSources: Array<{ src: string; type: string }> = []
        
        if (errorRetryCount === 1) {
          // First retry: basic MIME type without codec specification
          fallbackSources = [
            { src: props.src, type: basicMimeType },
            { src: props.src, type: 'video/mp4' }, // Universal fallback
            { src: props.src, type: 'video/webm' }
          ]
        } else if (errorRetryCount === 2 && basicMimeType === 'video/x-matroska') {
          // Second retry for MKV: try as MP4 (some servers misidentify containers)
          fallbackSources = [
            { src: props.src, type: 'video/mp4; codecs="hvc1.1.6.L93.B0"' },
            { src: props.src, type: 'video/mp4; codecs="avc1.64001F"' },
            { src: props.src, type: 'video/mp4' }
          ]
        } else if (errorRetryCount === 3) {
          // Final retry: completely generic
          fallbackSources = [
            { src: props.src, type: 'application/octet-stream' },
            { src: props.src, type: '' } // Let browser decide
          ]
        }
        
        if (fallbackSources.length > 0) {
          console.log('[VideoPlayer] Trying fallback sources:', fallbackSources)
          player?.src(fallbackSources)
        }
      } else if (playerError.code === 4 && errorRetryCount >= maxRetries) {
        // Show user-friendly error message
        console.error('[VideoPlayer] All source recovery attempts failed')
        showMediaError('这个视频文件无法播放。可能是编码格式不被浏览器支持，或文件已损坏。')
      }
    }
  })

  // Log successful source selection
  player.on('loadstart', () => {
    console.log('[VideoPlayer] Video source loading started')
  })

  player.on('canplay', () => {
    console.log('[VideoPlayer] Video can play - codec supported!')
  })

  let chapterDisplayComponent: any = null

  player.on('timeupdate', () => {
    const t = player!.currentTime()
    if (typeof t === 'number') {
      emit('time-update', t)
      const oldChapter = currentChapter.value
      updateCurrentChapter(t)

      // Update chapter display when chapter changes or component is found for first time
      if (!chapterDisplayComponent) {
        chapterDisplayComponent = player!.getChild('controlBar')?.getChild('ChapterDisplay')
      }
      
      if (chapterDisplayComponent && typeof (chapterDisplayComponent as any).updateContent === 'function') {
        // Update if chapter changed or if it's the first time
        if (oldChapter?.id !== currentChapter.value?.id) {
          (chapterDisplayComponent as any).updateContent()
        }
      }
    }
  })

  // Handle video end event for autoplay functionality
  player.on('ended', () => {
    console.log('[VideoPlayer] Video ended, checking autoplay settings')
    if (isAutoPlayEnabled.value) {
      console.log('[VideoPlayer] Autoplay enabled, requesting next video')
      emit('autoplay-next')
    } else {
      console.log('[VideoPlayer] Autoplay disabled, staying on current video')
    }
  })

  // Initialize chapter markers when ready
  player.ready(() => {
    setTimeout(() => {
      chapterDisplayComponent = player!.getChild('controlBar')?.getChild('ChapterDisplay')
      if (chapterDisplayComponent && typeof (chapterDisplayComponent as any).updateContent === 'function') {
        updateCurrentChapter(player!.currentTime() || 0)
        ;(chapterDisplayComponent as any).updateContent()
      }
      addChapterMarkers()
    }, 100)
    
    // Add fullscreen change event listeners for iOS compatibility
    player!.on('fullscreenchange', () => {
      const isFullscreen = player!.isFullscreen()
      console.log('[VideoPlayer] Fullscreen change:', isFullscreen)
      emit('fullscreen-change', !!isFullscreen)
    })
    
    // Also listen to native fullscreen events for better iOS support
    const videoElement = player!.el().querySelector('video')
    if (videoElement) {
      videoElement.addEventListener('webkitfullscreenchange', () => {
        const isFullscreen = !!(document as any).webkitFullscreenElement || !!(videoElement as any).webkitDisplayingFullscreen
        console.log('[VideoPlayer] WebKit fullscreen change:', isFullscreen)
        emit('fullscreen-change', !!isFullscreen)
      })
    }
  })
  console.log(props.blobUrls)
  updateSubtitleTracks(player, props.blobUrls)

  // 禁用Video.js原生字幕样式设置，只保留字幕开关功能
  if (player) {
    player.ready(() => {
      setTimeout(() => {
        if (!player) return
        
        // 找到字幕按钮并禁用样式设置功能
        const subsCapsButton = player.getChild('controlBar')?.getChild('subsCapsButton')
        if (subsCapsButton) {
          // 获取字幕菜单
          const menu = (subsCapsButton as any).menu
          if (menu) {
            // 隐藏字幕样式设置按钮
            const menuItems = menu.children()
            menuItems.forEach((item: any) => {
              if (item.hasClass && item.hasClass('vjs-texttrack-settings')) {
                item.hide()
                item.el().style.display = 'none'
              }
            })
            
            // 移除样式设置菜单项
            const settingsMenuItem = menu.el().querySelector('.vjs-texttrack-settings')
            if (settingsMenuItem) {
              settingsMenuItem.remove()
            }
          }
          
          // 直接从DOM中移除设置按钮
          const controlBar = player.getChild('controlBar')?.el()
          if (controlBar) {
            const settingsButton = controlBar.querySelector('.vjs-texttrack-settings')
            if (settingsButton) {
              settingsButton.remove()
            }
          }
        }
      }, 100)
    })
  }

  // Setup background play functionality
  setupBackgroundPlay()

  // Load chapters if videoId is provided
  if (props.videoId) {
    loadChapters()
  }

  // 确保字幕样式正确应用
  injectGlobalSubtitleStyles()
})

// Load chapters function
const loadChapters = async () => {
  if (props.videoId && props.videoId > 0) {
    try {
      const loadedChapters = await ChapterAPI.loadChapters(props.videoId)
      chapters.value = loadedChapters
      console.log(`[VideoPlayer] Loaded ${loadedChapters.length} chapters:`, loadedChapters.map(c => ({ id: c.id, title: c.title, startTime: c.startTime, endTime: c.endTime })))
      console.log('[VideoPlayer] Full chapter data:', loadedChapters)
      
      // Update current chapter after loading new chapters
      if (player) {
        updateCurrentChapter(player.currentTime() || 0)
        // Also update the chapter display component
        const chapterDisplayComponent = player.getChild('controlBar')?.getChild('ChapterDisplay')
        if (chapterDisplayComponent && typeof (chapterDisplayComponent as any).updateContent === 'function') {
          (chapterDisplayComponent as any).updateContent()
        }
      }
    } catch (error) {
      console.error('Failed to load chapters:', error)
    }
  }
}

// Watch for videoId changes and reload chapters
watch(
  () => props.videoId,
  () => {
    if (props.videoId) {
      loadChapters()
    }
  },
  { immediate: false },
)

// Watch for chapters changes and update markers
watch(
  () => chapters.value,
  () => {
    // Delay to ensure player is ready
    setTimeout(() => {
      if (player && player.duration()) {
        addChapterMarkers()
      }
    }, 100)
  },
  { deep: true },
)

// whenever the video URL changes
watch(
  () => props.src,
  (src) => {
    const sources = getVideoSources(src)
    player?.src(sources)
  },
)
watch(
  () => props.blobUrls, // getter：返回最新值
  (newUrls, oldUrls) => {
    // callback：拿到新旧值
    console.log('blobUrls changed:', newUrls, oldUrls)
    // 这里根据 newUrls 做真正的更新
    updateSubtitleTracks(player, newUrls)
  },
  { deep: false, immediate: false }, // 选项可省根据需要添加
)

function getCurrentTime() {
  return player?.currentTime() ?? 0
}

// Chapter management functions
function formatTime(seconds: number) {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

function getCurrentChapter(time: number): Chapter | null {
  // Find all matching chapters, then select the one with the latest startTime
  const matchingChapters = chapters.value.filter(
    (chapter) =>
      time >= chapter.startTime &&
      (chapter.endTime === undefined || time < chapter.endTime),
  )
  
  // Sort by startTime descending and pick the first (latest)
  const current = matchingChapters.sort((a, b) => b.startTime - a.startTime)[0] || null
  
  if (time > 49 && time < 52) {
    console.log(`[VideoPlayer] Time: ${time.toFixed(2)}s - Checking chapters:`)
    chapters.value.forEach(ch => {
      console.log(`  Chapter "${ch.title}" (${ch.id}): start=${ch.startTime}s, end=${ch.endTime || 'undefined'}s, matches=${time >= ch.startTime && (ch.endTime === undefined || time < ch.endTime)}`)
    })
    console.log(`  -> Matching chapters: ${matchingChapters.length}, Selected: ${current?.id || 'none'} "${current?.title || 'none'}"`)
  }
  return current
}

function updateCurrentChapter(time: number) {
  currentTime.value = time
  const oldChapter = currentChapter.value
  currentChapter.value = getCurrentChapter(time)
  console.log(`[VideoPlayer] Current time: ${time.toFixed(2)}s, Old chapter: ${oldChapter?.id || 'none'}, New chapter: ${currentChapter.value?.id || 'none'}, Title: ${currentChapter.value?.title || 'none'}`)
}

// Add chapter markers to progress bar
function addChapterMarkers() {
  console.log(`[VideoPlayer] addChapterMarkers called - player: ${!!player}, chapters: ${chapters.value.length}`)
  
  if (!player || chapters.value.length === 0) {
    console.log(`[VideoPlayer] Early return - player: ${!!player}, chapters: ${chapters.value.length}`)
    return
  }

  const progressControl = player.getChild('controlBar')?.getChild('progressControl')
  const seekBar = progressControl?.getChild('seekBar')

  if (!seekBar) {
    console.log('[VideoPlayer] SeekBar not found, cannot add chapter markers')
    return
  }

  const duration = player.duration()
  console.log(`[VideoPlayer] Video duration: ${duration}`)
  if (!duration) {
    console.log('[VideoPlayer] No video duration, cannot add chapter markers')
    return
  }

  // Remove existing markers and gaps
  const existingMarkers = seekBar
    .el()
    .querySelectorAll('.chapter-marker, .chapter-gap, .chapter-hover-zone')
  existingMarkers.forEach((marker) => marker.remove())

  // Keep default Video.js tooltip behavior (show only time)
  // No custom tooltip modifications needed - Video.js will handle time display automatically

  // No gaps or interactive elements needed - just simple visual markers

  // No visual gaps mask needed - simple design with only black markers

  // Style progress bar with transparency and hover effects
  const loadProgressBar = seekBar.el().querySelector('.vjs-load-progress')
  if (loadProgressBar) {
    ;(loadProgressBar as HTMLElement).style.opacity = '0.7'
  }

  // Add simple chapter markers (small black blocks)
  console.log(`[VideoPlayer] Adding chapter markers for ${chapters.value.length} chapters`)
  chapters.value.forEach((chapter, index) => {
    if (index === 0) return // Skip first chapter, no marker needed

    const percentage = (chapter.startTime / duration) * 100
    console.log(`[VideoPlayer] Creating marker for chapter ${index + 1} at ${percentage.toFixed(1)}% (${chapter.startTime}s)`)

    // Create more visible black chapter marker
    const marker = document.createElement('div')
    marker.className = 'chapter-marker'
    marker.style.cssText = `
      position: absolute;
      left: ${percentage}%;
      top: 0;
      width: 3px;
      height: 100%;
      background-color: #000000 !important;
      z-index: 100;
      transform: translateX(-50%);
      pointer-events: none;
      opacity: 1;
      box-shadow: 0 0 2px rgba(255,255,255,0.5);
      border-left: 1px solid #000000;
      border-right: 1px solid #000000;
    `

    seekBar.el().appendChild(marker)
    console.log(`[VideoPlayer] Marker added for chapter "${chapter.title}" at ${percentage.toFixed(1)}%`)
  })
  
  console.log(`[VideoPlayer] Total markers added: ${chapters.value.length - 1}`)
}

// Custom Current Time Display with Edit Functionality
function createEditableTimeDisplay() {
  const vjsComponent = videojs.getComponent('Component')

  class EditableCurrentTimeDisplay extends vjsComponent {
    isEditing: boolean
    inputElement: HTMLInputElement | null

    constructor(player: any, options: any) {
      super(player, options)
      this.addClass('vjs-current-time-display')
      this.addClass('vjs-time-control')
      this.addClass('vjs-control')
      this.isEditing = false
      this.inputElement = null

      // Add double-click handler
      this.on('dblclick', this.startEdit.bind(this))

      // Update display on timeupdate
      this.player().on('timeupdate', this.updateDisplay.bind(this))
    }

    formatTime(seconds: number): string {
      if (isNaN(seconds) || seconds < 0) return '00:00'
      const mins = Math.floor(seconds / 60)
      const secs = Math.floor(seconds % 60)
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
    }

    parseTime(timeString: string): number | null {
      const timePattern = /^(\d{1,2}):(\d{2})$/
      const match = timeString.match(timePattern)
      if (!match) return null

      const minutes = parseInt(match[1], 10)
      const seconds = parseInt(match[2], 10)

      if (minutes < 0 || seconds < 0 || seconds >= 60) return null

      return minutes * 60 + seconds
    }

    startEdit() {
      if (this.isEditing) return

      this.isEditing = true
      const currentTime = this.player().currentTime() || 0
      const timeString = this.formatTime(currentTime)

      // Create input element
      this.inputElement = document.createElement('input')
      this.inputElement.type = 'text'
      this.inputElement.value = timeString
      this.inputElement.style.cssText = `
        background: rgba(0, 0, 0, 0.8);
        color: white;
        border: 1px solid #666;
        padding: 2px 4px;
        font-size: 11px;
        font-family: inherit;
        width: 45px;
        text-align: center;
        border-radius: 2px;
      `

      // Replace display with input
      const textElement = this.el().querySelector('.time-text') as HTMLElement
      if (textElement) {
        textElement.style.display = 'none'
      }
      this.el().appendChild(this.inputElement)

      // Focus and select all text
      this.inputElement.focus()
      this.inputElement.select()

      // Add event handlers
      this.inputElement.addEventListener('blur', this.finishEdit.bind(this))
      this.inputElement.addEventListener('keydown', this.handleKeydown.bind(this))
    }

    handleKeydown(e: KeyboardEvent) {
      if (e.key === 'Enter') {
        e.preventDefault()
        this.finishEdit()
      } else if (e.key === 'Escape') {
        e.preventDefault()
        this.cancelEdit()
      }
    }

    finishEdit() {
      if (!this.isEditing || !this.inputElement) return

      const newTimeString = this.inputElement.value.trim()
      const newTime = this.parseTime(newTimeString)

      if (newTime !== null) {
        const duration = this.player().duration() || 0
        const validTime = Math.max(0, Math.min(newTime, duration))
        this.player().currentTime(validTime)
      }

      this.cancelEdit()
    }

    cancelEdit() {
      if (!this.isEditing) return

      this.isEditing = false

      // Remove input element
      if (this.inputElement) {
        this.inputElement.remove()
        this.inputElement = null
      }

      // Show text element again
      const textElement = this.el().querySelector('.time-text') as HTMLElement
      if (textElement) {
        textElement.style.display = 'inline'
      }

      this.updateDisplay()
    }

    updateDisplay() {
      if (this.isEditing) return

      const currentTime = this.player().currentTime() || 0
      const textElement = this.el().querySelector('.time-text')
      if (textElement) {
        textElement.textContent = this.formatTime(currentTime)
      }
    }

    createEl() {
      const el = videojs.dom.createEl('div', {
        className: 'vjs-current-time-display vjs-time-control vjs-control',
        style: `
          cursor: pointer;
          user-select: none;
        `,
        title: 'Double-click to edit time',
      })

      const textEl = videojs.dom.createEl('span', {
        className: 'time-text',
        style: 'font-size: 11px; color: white;',
      })

      el.appendChild(textEl)
      return el
    }
  }

  videojs.registerComponent('EditableCurrentTimeDisplay', EditableCurrentTimeDisplay)
  return EditableCurrentTimeDisplay
}

// Custom Camera Snapshot Component
function createCameraSnapshotControl() {
  const vjsComponent = videojs.getComponent('Component')

  class CameraSnapshotControl extends vjsComponent {

    constructor(player: any, options: any) {
      super(player, options)
      this.addClass('vjs-camera-control')
      this.addClass('vjs-control')
      this.addClass('vjs-button')

      // Add click handler for snapshot
      this.on('click', this.takeSnapshot.bind(this))
    }

    async takeSnapshot() {
      try {
        const video = this.player().el().querySelector('video') as HTMLVideoElement
        if (!video) {
          console.error('Video element not found')
          this.showFeedback('Video element not found', true)
          return
        }

        // Check if video is loaded
        if (video.readyState < 2) {
          this.showFeedback('Video not ready for snapshot', true)
          return
        }

        // Try canvas method first
        try {
          await this.captureViaCanvas(video)
        } catch (canvasError) {
          console.error('Canvas method failed:', canvasError)
          // Try fallback method
          try {
            await this.captureViaScreenAPI(video)
          } catch (screenError) {
            console.error('Screen API method failed:', screenError)
            this.showFeedback('Snapshot capture failed - CORS or security restrictions', true)
          }
        }

      } catch (error) {
        console.error('Error taking snapshot:', error)
        this.showFeedback('Failed to take snapshot', true)
      }
    }

    async captureViaCanvas(video: HTMLVideoElement) {
      // Create canvas and draw current frame
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        throw new Error('Canvas context not available')
      }

      canvas.width = video.videoWidth || video.clientWidth
      canvas.height = video.videoHeight || video.clientHeight
      
      // This will throw SecurityError if video is tainted
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

      // Two-layer fallback strategy for copying images as actual images
      try {
        // Layer 1: Modern Clipboard API - copy as actual image (HTTPS environments)
        if ('clipboard' in navigator && 'write' in navigator.clipboard && 'ClipboardItem' in window) {
          await this.copyViaClipboardAPI(canvas)
          return
        }
        
        // Layer 2: Download as fallback
        throw new Error('Clipboard API not available, downloading instead')
        
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error'
        console.log('Copy method failed, downloading instead:', errorMessage)
        // Download as image file instead of copying as text
        canvas.toBlob((blob) => {
          if (blob) {
            this.downloadBlob(blob, 'video-snapshot.png')
          }
        }, 'image/png')
      }
    }

    async copyViaClipboardAPI(canvas: HTMLCanvasElement) {
      return new Promise<void>((resolve, reject) => {
        canvas.toBlob(async (blob) => {
          if (!blob) {
            reject(new Error('Failed to create image blob'))
            return
          }

          try {
            await navigator.clipboard.write([
              new ClipboardItem({
                'image/png': blob
              })
            ])
            
            this.showFeedback('Video snapshot copied as image to clipboard!')
            resolve()
          } catch (clipboardError) {
            reject(clipboardError)
          }
        }, 'image/png')
      })
    }

    downloadBlob(blob: Blob, filename: string) {
      // Create download link
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.style.display = 'none'
      
      // Trigger download
      document.body.appendChild(a)
      a.click()
      
      // Cleanup
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      
      this.showFeedback('Video snapshot downloaded as PNG file!')
    }

    async captureViaScreenAPI(_video: HTMLVideoElement) {
      // Fallback: try to use getDisplayMedia (requires user permission)
      if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
        throw new Error('Screen capture API not available')
      }

      try {
        // Request screen capture permission
        const stream = await navigator.mediaDevices.getDisplayMedia({
          video: {
            mediaSource: 'screen'
          }
        } as any)

        // Create video element for screen capture
        const captureVideo = document.createElement('video')
        captureVideo.srcObject = stream
        captureVideo.play()

        captureVideo.addEventListener('loadedmetadata', async () => {
          // Create canvas for screen capture
          const canvas = document.createElement('canvas')
          const ctx = canvas.getContext('2d')
          if (!ctx) {
            stream.getTracks().forEach(track => track.stop())
            throw new Error('Canvas context not available')
          }

          canvas.width = captureVideo.videoWidth
          canvas.height = captureVideo.videoHeight
          ctx.drawImage(captureVideo, 0, 0)

          // Stop screen capture
          stream.getTracks().forEach(track => track.stop())

          // Convert to blob and handle clipboard or download
          canvas.toBlob(async (blob) => {
            if (!blob) return

            // Check if clipboard API is available
            if (navigator.clipboard && navigator.clipboard.write && window.ClipboardItem) {
              try {
                await navigator.clipboard.write([
                  new ClipboardItem({
                    'image/png': blob
                  })
                ])
                this.showFeedback('Screen snapshot copied to clipboard!')
              } catch (error) {
                console.error('Failed to copy screen capture:', error)
                // Fall back to download
                this.downloadBlob(blob, 'screen-snapshot.png')
              }
            } else {
              // Download instead of clipboard
              this.downloadBlob(blob, 'screen-snapshot.png')
            }
          }, 'image/png')
        })

      } catch (error) {
        throw new Error(`Screen capture failed: ${error}`)
      }
    }

    showFeedback(message: string, isError: boolean = false) {
      // Create temporary feedback element
      const feedback = document.createElement('div')
      feedback.textContent = message
      feedback.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: ${isError ? 'rgba(220, 53, 69, 0.9)' : 'rgba(40, 167, 69, 0.9)'};
        color: white;
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 14px;
        z-index: 9999;
        pointer-events: none;
      `
      
      document.body.appendChild(feedback)
      
      // Remove after 3 seconds
      setTimeout(() => {
        if (feedback.parentNode) {
          feedback.parentNode.removeChild(feedback)
        }
      }, 3000)
    }

    createEl() {
      const el = videojs.dom.createEl('div', {
        className: 'vjs-camera-control vjs-control vjs-button',
        style: `
          position: relative;
          color: white;
          padding: 6px 8px;
          cursor: pointer;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 4px;
          margin: 0 2px;
          display: flex;
          align-items: center;
          justify-content: center;
          width: auto;
          height: auto;
        `,
        title: 'Copy video snapshot (requires HTTPS) or download',
      })

      // Create Camera icon using the provided SVG
      el.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
          <path d="M13.997 4a2 2 0 0 1 1.76 1.05l.486.9A2 2 0 0 0 18.003 7H20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1.997a2 2 0 0 0 1.759-1.048l.489-.904A2 2 0 0 1 10.004 4z"/>
          <circle cx="12" cy="13" r="3"/>
        </svg>
      `

      return el
    }
  }

  videojs.registerComponent('CameraSnapshotControl', CameraSnapshotControl)
  return CameraSnapshotControl
}

// Custom Video Settings Control Component
function createVideoSettingsControl() {
  const vjsComponent = videojs.getComponent('Component')

  class VideoSettingsControl extends vjsComponent {
    dropdownVisible: boolean

    constructor(player: any, options: any) {
      super(player, options)
      this.addClass('vjs-settings-control')
      this.addClass('vjs-control')
      this.addClass('vjs-button')
      this.dropdownVisible = false

      // Add click handler for dropdown
      this.on('click', this.toggleDropdown.bind(this))

      // Close dropdown when clicking outside
      document.addEventListener('click', (e) => {
        const element = this.el()
        if (element && !element.contains(e.target as Node)) {
          this.hideDropdown()
        }
      })
    }

    toggleDropdown() {
      if (this.dropdownVisible) {
        this.hideDropdown()
      } else {
        this.showDropdown()
      }
    }

    showDropdown() {
      this.dropdownVisible = true
      let dropdown = this.el().querySelector('.settings-dropdown')
      if (!dropdown) {
        dropdown = this.createDropdown()
        this.el().appendChild(dropdown)
      }
      ;(dropdown as HTMLElement).style.display = 'block'
    }

    hideDropdown() {
      this.dropdownVisible = false
      const dropdown = this.el().querySelector('.settings-dropdown')
      if (dropdown) {
        ;(dropdown as HTMLElement).style.display = 'none'
      }
    }

    createDropdown() {
      console.log('[VideoSettings] Creating settings dropdown menu')
      const dropdown = videojs.dom.createEl('div', {
        className: 'settings-dropdown',
        style: `
          position: absolute;
          bottom: 100%;
          left: 50%;
          transform: translateX(-50%);
          background: rgba(0, 0, 0, 0.63);
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: 4px;
          min-width: 160px;
          z-index: 1000;
          margin-bottom: 5.6px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.21);
        `,
      })

      // Background play option - only keep this one since play mode is handled by separate control
      const backgroundPlayItem = videojs.dom.createEl('div', {
        className: 'settings-dropdown-item',
        style: `
          padding: 8px 16px;
          cursor: pointer;
          color: white;
          font-size: 12px;
          transition: background-color 0.2s;
          display: flex;
          align-items: center;
          justify-content: space-between;
        `,
      })

      const backgroundPlayLabel = videojs.dom.createEl('span', {
        textContent: '后台播放'
      })

      const backgroundPlayToggle = videojs.dom.createEl('span', {
        className: 'toggle-indicator',
        textContent: isBackgroundPlayEnabled.value ? '✓' : '',
        style: `
          color: ${isBackgroundPlayEnabled.value ? '#4CAF50' : 'rgba(255, 255, 255, 0.3)'};
          font-weight: bold;
        `
      })

      backgroundPlayItem.appendChild(backgroundPlayLabel)
      backgroundPlayItem.appendChild(backgroundPlayToggle)

      // Add hover effect
      this.addHoverEffect(backgroundPlayItem as HTMLElement)

      // Add click handler
      backgroundPlayItem.addEventListener('click', (e) => {
        e.stopPropagation()
        this.toggleBackgroundPlay()
        this.updateToggleIndicator(backgroundPlayToggle as HTMLElement, isBackgroundPlayEnabled.value)
      })

      dropdown.appendChild(backgroundPlayItem)

      return dropdown
    }

    addHoverEffect(item: HTMLElement) {
      item.addEventListener('mouseenter', () => {
        item.style.backgroundColor = 'rgba(255, 255, 255, 0.1)'
      })

      item.addEventListener('mouseleave', () => {
        item.style.backgroundColor = 'transparent'
      })
    }

    updateToggleIndicator(toggle: HTMLElement, isEnabled: boolean) {
      toggle.textContent = isEnabled ? '✓' : ''
      toggle.style.color = isEnabled ? '#4CAF50' : 'rgba(255, 255, 255, 0.3)'
    }

    toggleBackgroundPlay() {
      isBackgroundPlayEnabled.value = !isBackgroundPlayEnabled.value
      console.log(`[VideoSettings] Background play: ${isBackgroundPlayEnabled.value ? 'enabled' : 'disabled'}`)
    }

    createEl() {
      const el = videojs.dom.createEl('div', {
        className: 'vjs-settings-control vjs-control vjs-button',
        style: `
          position: relative;
          color: white;
          padding: 6px 8px;
          cursor: pointer;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 4px;
          margin: 0 2px;
          display: flex;
          align-items: center;
          justify-content: center;
          width: auto;
          height: auto;
        `,
        title: 'Video settings',
      })

      // Create Settings icon
      el.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
          <path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
      `

      return el
    }
  }

  videojs.registerComponent('VideoSettingsControl', VideoSettingsControl)
  return VideoSettingsControl
}

// Custom Video Speed Control Component
function createVideoSpeedControl() {
  const vjsComponent = videojs.getComponent('Component')

  class VideoSpeedControl extends vjsComponent {
    dropdownVisible: boolean
    speedOptions: number[]

    constructor(player: any, options: any) {
      super(player, options)
      this.addClass('vjs-speed-control')
      this.addClass('vjs-control')
      this.addClass('vjs-button')
      this.dropdownVisible = false
      this.speedOptions = [0.1, 0.5, 1, 1.5, 2, 4]

      // Add click handler for dropdown
      this.on('click', this.toggleDropdown.bind(this))

      // Close dropdown when clicking outside
      document.addEventListener('click', (e) => {
        const element = this.el()
        if (element && !element.contains(e.target as Node)) {
          this.hideDropdown()
        }
      })

      // Update display when playback rate changes
      this.player().on('ratechange', this.updateDisplay.bind(this))
    }

    toggleDropdown() {
      if (this.dropdownVisible) {
        this.hideDropdown()
      } else {
        this.showDropdown()
      }
    }

    showDropdown() {
      this.dropdownVisible = true
      let dropdown = this.el().querySelector('.speed-dropdown')
      if (!dropdown) {
        dropdown = this.createDropdown()
        this.el().appendChild(dropdown)
      }
      ;(dropdown as HTMLElement).style.display = 'block'
    }

    hideDropdown() {
      this.dropdownVisible = false
      const dropdown = this.el().querySelector('.speed-dropdown')
      if (dropdown) {
        ;(dropdown as HTMLElement).style.display = 'none'
      }
    }

    createDropdown() {
      const dropdown = videojs.dom.createEl('div', {
        className: 'speed-dropdown',
        style: `
          position: absolute;
          bottom: 100%;
          left: 50%;
          transform: translateX(-50%);
          background: rgba(0, 0, 0, 0.63);
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: 4px;
          min-width: 56px;
          max-height: 140px;
          overflow-y: auto;
          z-index: 1000;
          margin-bottom: 5.6px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.21);
        `,
      })

      this.speedOptions.forEach((speed) => {
        const speedItem = videojs.dom.createEl('div', {
          className: 'speed-dropdown-item',
          style: `
            padding: 8px 16px;
            cursor: pointer;
            color: white;
            font-size: 12px;
            text-align: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            transition: background-color 0.2s;
          `,
        })

        const speedText = speed === 1 ? 'Normal' : `${speed}x`
        speedItem.textContent = speedText

        // Highlight current speed
        const currentRate = this.player().playbackRate() || 1
        if (Math.abs(currentRate - speed) < 0.01) {
          (speedItem as HTMLElement).style.backgroundColor = 'rgba(255, 255, 255, 0.2)'
          ;(speedItem as HTMLElement).style.fontWeight = 'bold'
        }

        // Add hover effect
        speedItem.addEventListener('mouseenter', () => {
          if (Math.abs(currentRate - speed) >= 0.01) {
            (speedItem as HTMLElement).style.backgroundColor = 'rgba(255, 255, 255, 0.1)'
          }
        })

        speedItem.addEventListener('mouseleave', () => {
          if (Math.abs(currentRate - speed) >= 0.01) {
            (speedItem as HTMLElement).style.backgroundColor = 'transparent'
          }
        })

        // Add click handler
        speedItem.addEventListener('click', (e) => {
          e.stopPropagation()
          this.player().playbackRate(speed)
          this.hideDropdown()
          this.updateDisplay()
        })

        dropdown.appendChild(speedItem)
      })

      return dropdown
    }

    updateDisplay() {
      // Update dropdown if visible
      if (this.dropdownVisible) {
        this.hideDropdown()
        this.showDropdown()
      }
    }

    createEl() {
      const el = videojs.dom.createEl('div', {
        className: 'vjs-speed-control vjs-control vjs-button',
        style: `
          position: relative;
          color: white;
          padding: 6px 8px;
          cursor: pointer;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 4px;
          margin: 0 2px;
          display: flex;
          align-items: center;
          justify-content: center;
          width: auto;
          height: auto;
        `,
        title: 'Playback speed',
      })

      // Create Gauge icon using the provided SVG
      el.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
          <path d="m12 14 4-4"/>
          <path d="M3.34 19a10 10 0 1 1 17.32 0"/>
        </svg>
      `

      return el
    }
  }

  videojs.registerComponent('VideoSpeedControl', VideoSpeedControl)
  return VideoSpeedControl
}

// Custom Play Mode Toggle Control Component
function createPlayModeToggleControl() {
  const vjsComponent = videojs.getComponent('Component')

  class PlayModeToggleControl extends vjsComponent {
    playMode: number // 0: 观后即停, 1: 单集循环, 2: 顺序播放

    constructor(player: any, options: any) {
      super(player, options)
      this.addClass('vjs-playmode-control')
      this.addClass('vjs-control')
      this.addClass('vjs-button')
      this.playMode = 0 // Start with 观后即停

      // Add click handler for toggle
      this.on('click', this.togglePlayMode.bind(this))
    }

    togglePlayMode() {
      // Cycle through: 观后即停 -> 单集循环 -> 顺序播放 -> 观后即停
      this.playMode = (this.playMode + 1) % 3
      const player = this.player()

      if (this.playMode === 0) {
        // 观后即停: Disable both loop and autoplay
        if (player) {
          player.loop(false)
        }
        if (isAutoPlayEnabled.value) {
          isAutoPlayEnabled.value = false
          emit('autoplay-settings-changed', false)
        }
        console.log('[PlayModeToggle] Stop after watching mode enabled')
      } else if (this.playMode === 1) {
        // 单集循环: Enable single loop
        if (player) {
          player.loop(true)
        }
        if (isAutoPlayEnabled.value) {
          isAutoPlayEnabled.value = false
          emit('autoplay-settings-changed', false)
        }
        console.log('[PlayModeToggle] Single loop mode enabled')
      } else {
        // 顺序播放: Enable sequential play (disable loop, enable autoplay)
        if (player) {
          player.loop(false)
        }
        isAutoPlayEnabled.value = true
        emit('autoplay-settings-changed', true)
        console.log('[PlayModeToggle] Sequential play mode enabled')
      }

      this.updateDisplay()
    }

    updateDisplay() {
      const textEl = this.el().querySelector('.playmode-text')
      const iconEl = this.el().querySelector('.playmode-icon')

      if (textEl && iconEl) {
        if (this.playMode === 0) {
          // 观后即停
          textEl.textContent = '观后即停'
          iconEl.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="6" height="6" x="9" y="9"/>
            </svg>
          `
          ;(this.el() as HTMLElement).style.backgroundColor = 'rgba(244, 67, 54, 0.3)'
        } else if (this.playMode === 1) {
          // 单集循环
          textEl.textContent = '单集循环'
          iconEl.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 19H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>
              <path d="M13 5l3 3-3 3"/>
              <path d="M18 8h-3a2 2 0 0 0-2 2v6"/>
            </svg>
          `
          ;(this.el() as HTMLElement).style.backgroundColor = 'rgba(76, 175, 80, 0.3)'
        } else {
          // 顺序播放
          textEl.textContent = '顺序播放'
          iconEl.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 4h4v12H5z"/>
              <path d="M13 4v12l6-6z"/>
            </svg>
          `
          ;(this.el() as HTMLElement).style.backgroundColor = 'rgba(0, 0, 0, 0.3)'
        }
      }
    }

    createEl() {
      const el = videojs.dom.createEl('div', {
        className: 'vjs-playmode-control vjs-control vjs-button',
        style: `
          position: relative;
          color: white;
          padding: 6px 8px;
          cursor: pointer;
          background: rgba(244, 67, 54, 0.3);
          border-radius: 4px;
          margin: 0 2px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 4px;
          width: auto;
          height: auto;
          transition: background-color 0.3s ease;
        `,
        title: 'Toggle between stop after watching, single loop and sequential play',
      })

      const iconEl = videojs.dom.createEl('span', {
        className: 'playmode-icon',
        innerHTML: `
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="6" height="6" x="9" y="9"/>
          </svg>
        `
      })

      const textEl = videojs.dom.createEl('span', {
        className: 'playmode-text',
        textContent: '观后即停',
        style: 'font-size: 11px; font-weight: 500;'
      })

      el.appendChild(iconEl)
      el.appendChild(textEl)

      return el
    }
  }

  videojs.registerComponent('PlayModeToggleControl', PlayModeToggleControl)
  return PlayModeToggleControl
}

// Custom Chapter Display with Dropdown for Video.js
function createChapterDisplay() {
  const vjsComponent = videojs.getComponent('Component')

  class ChapterDisplay extends vjsComponent {
    dropdownVisible: boolean

    constructor(player: any, options: any) {
      super(player, options)
      this.addClass('vjs-chapter-display')
      this.el().setAttribute('title', 'Click to select chapter')
      this.dropdownVisible = false
      this.updateContent()

      // Add click handler for dropdown
      this.on('click', this.toggleDropdown.bind(this))

      // Close dropdown when clicking outside
      document.addEventListener('click', (e) => {
        const element = this.el()
        if (element && !element.contains(e.target as Node)) {
          this.hideDropdown()
        }
      })
    }

    toggleDropdown() {
      if (this.dropdownVisible) {
        this.hideDropdown()
      } else {
        this.showDropdown()
      }
    }

    showDropdown() {
      this.dropdownVisible = true
      let dropdown = this.el().querySelector('.chapter-dropdown')
      if (!dropdown) {
        dropdown = this.createDropdown()
        this.el().appendChild(dropdown)
      }
      ;(dropdown as HTMLElement).style.display = 'block'
    }

    hideDropdown() {
      this.dropdownVisible = false
      const dropdown = this.el().querySelector('.chapter-dropdown')
      if (dropdown) {
        ;(dropdown as HTMLElement).style.display = 'none'
      }
    }

    createDropdown() {
      const dropdown = videojs.dom.createEl('div', {
        className: 'chapter-dropdown',
        style: `
          position: absolute;
          bottom: 100%;
          left: 0;
          background: rgba(0, 0, 0, 0.63);
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: 4px;
          min-width: 210px;
          max-height: 140px;
          overflow-y: auto;
          z-index: 1000;
          margin-bottom: 5.6px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.21);
        `,
      })

      chapters.value.forEach((chapter, index) => {
        const chapterItem = videojs.dom.createEl('div', {
          className: 'chapter-dropdown-item',
          style: `
            padding: 8px 12px;
            cursor: pointer;
            color: white;
            font-size: 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            transition: background-color 0.2s;
          `,
        })

        const chapterNumber = index + 1
        const startTime = formatTime(chapter.startTime)
        const endTime = chapter.endTime ? formatTime(chapter.endTime) : ''
        const timeRange = endTime ? `${startTime}-${endTime}` : `${startTime}-`

        chapterItem.innerHTML = `
          <div style="font-weight: bold; margin-bottom: 2px;">Chapter${chapterNumber}: "${chapter.title}"</div>
          <div style="color: rgba(255, 255, 255, 0.7); font-size: 10px;">${timeRange}</div>
        `

        // Highlight current chapter
        if (currentChapter.value && currentChapter.value.id === chapter.id) {
          ;(chapterItem as HTMLElement).style.backgroundColor = 'rgba(255, 255, 255, 0.2)'
        }

        // Add hover effect
        chapterItem.addEventListener('mouseenter', () => {
          if (currentChapter.value?.id !== chapter.id) {
            ;(chapterItem as HTMLElement).style.backgroundColor = 'rgba(255, 255, 255, 0.1)'
          }
        })

        chapterItem.addEventListener('mouseleave', () => {
          if (currentChapter.value?.id !== chapter.id) {
            ;(chapterItem as HTMLElement).style.backgroundColor = 'transparent'
          }
        })

        // Add click handler
        chapterItem.addEventListener('click', (e) => {
          e.stopPropagation()
          if (this.player()) {
            this.player().currentTime(chapter.startTime)
          }
          this.hideDropdown()
        })

        dropdown.appendChild(chapterItem)
      })

      return dropdown
    }

    updateContent() {
      const chapter = currentChapter.value
      console.log(`[ChapterDisplay] updateContent called, current chapter:`, chapter?.id || 'none', chapter?.title || 'none')
      if (chapter) {
        const chapterNumber = chapters.value.findIndex((c) => c.id === chapter.id) + 1
        const startTime = formatTime(chapter.startTime)
        const endTime = chapter.endTime ? formatTime(chapter.endTime) : ''
        const timeRange = endTime ? `${startTime}-${endTime}` : `${startTime}-`
        this.el().querySelector('.chapter-text')!.innerHTML =
          `Chapter${chapterNumber}: "${chapter.title}" on ${timeRange}`
      } else {
        this.el().querySelector('.chapter-text')!.innerHTML =
          chapters.value.length > 0 ? 'Click to select chapter' : 'No chapters'
      }

      // Update dropdown if visible
      if (this.dropdownVisible) {
        this.hideDropdown()
        this.showDropdown()
      }
    }

    createEl() {
      const el = videojs.dom.createEl('div', {
        className: 'vjs-chapter-display vjs-control vjs-button',
        style: `
          position: relative;
          color: white; 
          font-size: 12px; 
          line-height: 1.4; 
          padding: 8px 12px; 
          white-space: nowrap; 
          cursor: pointer;
          background: rgba(0,0,0,0.3);
          border-radius: 4px;
          margin: 0 4px;
          min-width: fit-content;
          max-width: 400px;
          flex-shrink: 0;
          align-self: center;
          top: 2px;
        `,
      })

      const textEl = videojs.dom.createEl('span', {
        className: 'chapter-text',
      })

      const arrowEl = videojs.dom.createEl('span', {
        innerHTML: ' ▼',
        style: 'margin-left: 8px; font-size: 10px;',
      })

      el.appendChild(textEl)
      el.appendChild(arrowEl)

      return el
    }
  }

  videojs.registerComponent('ChapterDisplay', ChapterDisplay)
  return ChapterDisplay
}

onBeforeUnmount(() => {
  // Clean up hotkeys
  if (hotkeyCleanup) {
    hotkeyCleanup()
  }
  // Clean up player
  player?.dispose()
})
</script>

<template>
  <!-- the ref name must match the one in <script> -->
  <!-- give w-full h-full to div wrapper can Resist videojs overflowing -->
  <div class="relative w-full h-full">
    <video ref="videoEl" class="video-js vjs-luxmty vjs-fill w-full h-full" crossorigin="anonymous" />
    
    <!-- Hotkey hint display -->
    <div 
      v-if="hotkeyHintVisible"
      class="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50 pointer-events-none"
      style="background: rgba(0, 0, 0, 0.8); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6);"
    >
      <div class="px-4 py-2 text-white text-lg font-medium rounded-lg">
        {{ hotkeyHintText }}
      </div>
    </div>
  </div>
</template>
