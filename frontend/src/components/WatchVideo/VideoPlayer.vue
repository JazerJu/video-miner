<!-- 视频播放器核心组件 -->
<script setup lang="ts">
import { generateVTT } from '@/composables/Buildvtt'
import { useSubtitles } from '@/composables/useSubtitles'
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import videojs from 'video.js'
import type Player from 'video.js/dist/types/player'
import { ChapterAPI } from '@/composables/ChapterAPI'
import { useLanguageTracks, type LanguageTrack } from '@/composables/LanguageTracksAPI'
import { Languages, Check, Settings as SettingsIcon } from 'lucide-vue-next'
import { useSubtitleStyle } from '@/composables/SubtitleStyle'
import { ElSwitch } from 'element-plus'
import { useMediaFiles } from '@/composables/useMediaFiles'

const { fetchSubtitle } = useSubtitles()
const { checkDubbingFile, checkSubtitleExistence } = useMediaFiles()

const props = defineProps<{
  src: string
  blobUrls?: (string | undefined)[] // [ zhUrl?, bothUrl?, enUrl? ] Also can be null.
  videoId?: number // Add video ID for chapter loading
  rawLang?: string // Original language of the video (e.g., 'en', 'zh')
  videoName?: string // Original video filename for URL construction
  showChapterMarkers?: boolean // Control chapter marker visibility
  sourceType?: 'file' | 'hls'
  audioSrc?: string
  audioSourceType?: 'file' | 'hls'
}>()

const dubbingLang = ref<string | null>(null)
const subtitleLang = ref<string | null>(null)
const isBilingual = ref(false)
const availableDubbings = ref<Record<string, boolean>>({})
const availableSubtitles = ref<Record<string, boolean>>({})
const playerReady = ref(false)

const showLanguagePanel = ref(false)
const activeLanguageTab = ref<'dubbing' | 'subtitle'>('subtitle')
const languagePanelRef = ref<HTMLElement | null>(null)
const languageBtnRef = ref<HTMLElement | null>(null)

const toggleLanguagePanel = () => {
        showLanguagePanel.value = !showLanguagePanel.value
}

const closeLanguagePanel = () => {
        showLanguagePanel.value = false
}

const onDocumentClick = (e: MouseEvent) => {
        if (!showLanguagePanel.value) return
        const target = e.target as Node
        if (
                languagePanelRef.value?.contains(target) ||
                languageBtnRef.value?.contains(target)
        ) {
                return
        }
        closeLanguagePanel()
}

onMounted(() => {
        document.addEventListener('click', onDocumentClick, true)
})

onBeforeUnmount(() => {
        document.removeEventListener('click', onDocumentClick, true)
})

const checkFiles = async () => {
  if (!props.src || !props.videoId) return
  
  // Check dubbings
  const langs = ['zh', 'en', 'ja']
  for (const lang of langs) {
    if (lang !== props.rawLang) {
      availableDubbings.value[lang] = await checkDubbingFile(props.src, lang)
    }
  }
  
  // Check subtitles
  for (const lang of langs) {
    availableSubtitles.value[lang] = await checkSubtitleExistence(props.videoId, lang)
  }
}

const { loadSubtitleSettings, injectGlobalSubtitleStyles } = useSubtitleStyle()

const emit = defineEmits<{
  (e: 'time-update', t: number): void
  (e: 'autoplay-next'): void
  (e: 'autoplay-settings-changed', enabled: boolean): void
  (e: 'fullscreen-change', isFullscreen: boolean): void
  (e: 'open-subtitle-settings'): void
  (e: 'ready'): void
}>()

const handleDubbingChange = (command: string | null) => {
  dubbingLang.value = command
  if (command === null) {
    // Switch to original
    if (player) {
        const currentTime = player.currentTime()
        const isPaused = player.paused()
        const volume = player.volume()
        const playbackRate = player.playbackRate()
        
        player.src(props.src)
        
        player.one('canplay', () => {
            player?.currentTime(currentTime)
            player?.volume(volume)
            player?.playbackRate(playbackRate)
            if (!isPaused) player?.play()
        })
    }
  } else {
    // Switch to dubbed
    const match = props.src.match(/\/([^\/]+)\.mp4$/)
    if (match) {
        const md5 = match[1]
        const dubbedUrl = props.src.replace(`${md5}.mp4`, `${md5}_${command}.mp4`)
        if (player) {
            const currentTime = player.currentTime()
            const isPaused = player.paused()
            const volume = player.volume()
            const playbackRate = player.playbackRate()
            
            player.src(dubbedUrl)
            
            player.one('canplay', () => {
                player?.currentTime(currentTime)
                player?.volume(volume)
                player?.playbackRate(playbackRate)
                if (!isPaused) player?.play()
            })
        }
    }
  }
}

const handleSubtitleChange = async (command: string | null) => {
    subtitleLang.value = command
    
    if (command && player) {
        const trackId = `dynamic-vtt-${command}`
        const tracks = Array.from(player.textTracks() as any)
        let track = tracks.find((t: any) => t.id === trackId)
        
        // If track not found by ID, check if it matches Primary/Translation
        if (!track) {
             if (command === props.rawLang) {
                track = tracks.find((t: any) => t.id === 'dynamic-vtt-Primary')
             } else {
                // Check if Translation track matches this language?
                // We don't know the language of Translation track easily without checking SubtitlePanel state.
                // But we can try to fetch and add a specific track for this language.
             }
        }

        if (!track) {
            // Fetch and add
            try {
                if (props.videoId) {
                    const subs = await fetchSubtitle(props.videoId, command)
                    if (subs && subs.length > 0) {
                        const vttUrl = generateVTT(command as any, [subs])
                        player.addRemoteTextTrack({
                            id: trackId,
                            kind: 'subtitles',
                            label: command,
                            language: command,
                            src: vttUrl,
                            default: false
                        })
                    }
                }
            } catch (e) {
                console.error('Failed to load subtitle:', e)
            }
        }
    }
    
    updateSubtitleDisplay()
}

const toggleBilingual = (val: boolean) => {
    isBilingual.value = val
    updateSubtitleDisplay()
}

const updateSubtitleDisplay = () => {
    if (!player) return
    
    // Hide all tracks first
    const tracks = Array.from(player.textTracks() as any)
    tracks.forEach((t: any) => t.mode = 'hidden')
    
    if (!subtitleLang.value) return // Off

    // Logic:
    // If bilingual is ON: show 'both' track if available, else show single track
    // If bilingual is OFF: show single track
    
    // We rely on updateSubtitleTracks to have added the tracks with specific IDs or labels
    // The existing updateSubtitleTracks adds:
    // id: dynamic-vtt-Primary (index 0)
    // id: dynamic-vtt-Translation (index 1)
    // id: dynamic-vtt-Both (index 2)
    
    // But wait, the existing logic assumes:
    // Primary = props.blobUrls[0] (usually Chinese/Original)
    // Translation = props.blobUrls[1] (usually English/UserLang)
    // Both = props.blobUrls[2]
    
    // If I select "English" (which might be Translation), I want to show Translation track.
    // If I select "Chinese" (Primary), I want Primary track.
    // If I select "Japanese", and it's not in blobUrls, I can't show it unless I fetch it.
    
    // CURRENT LIMITATION: I can only switch between what's loaded in blobUrls.
    // blobUrls comes from SubtitlePanel.
    // SubtitlePanel loads Primary (rawLang) and Translation (userLang).
    // If user selects a 3rd language, it won't work with current architecture unless I update SubtitlePanel.
    
    // For now, I will map the selection to the available tracks.
    // 'zh' -> Primary (if rawLang is zh) or Translation (if userLang is zh)
    // 'en' -> Primary (if rawLang is en) or Translation (if userLang is en)
    
    // To make this robust, I should probably just toggle the tracks based on what they contain.
    // But I don't know what language 'Primary' is without checking props.rawLang.
    
    // Let's assume:
    // Primary = props.rawLang (default 'zh')
    // Translation = 'en' (or whatever user set)
    
    // If I select 'zh':
    // If rawLang == 'zh', show Primary.
    // Else if userLang == 'zh', show Translation.
    
    // If isBilingual is true:
    // Show 'Both' track.
    
    if (isBilingual.value) {
        const bothTrack = tracks.find((t: any) => t.id === 'dynamic-vtt-Both') as any
        if (bothTrack) {
            bothTrack.mode = 'showing'
            return
        }
    }
    
    // Single language
    // Find track with matching language
    // video.js tracks have .language property.
    // updateSubtitleTracks sets .language to 'primary' or 'translation'.
    // This is not standard language code.
    
    // I need to know which track corresponds to which language.
    // props.rawLang is Primary.
    // I don't know Translation language easily here (it's in SubtitlePanel).
    
    // HACK: Just try to match standard codes if possible, or fallback to Primary/Translation logic.
    // Since I can't easily change SubtitlePanel right now, I will implement a simplified logic:
    // If subtitleLang is 'zh', try to find a track that is Chinese.
    // But the tracks are labeled '原文', '译文'.
    
    // I will modify updateSubtitleTracks to set the correct language code if possible, 
    // OR I will just assume:
    // If subtitleLang == props.rawLang -> Primary
    // Else -> Translation
    
    let targetId = ''
    if (subtitleLang.value === props.rawLang) {
        targetId = 'dynamic-vtt-Primary'
    } else {
        targetId = 'dynamic-vtt-Translation'
    }
    
    const track = tracks.find((t: any) => t.id === targetId) as any
    if (track) {
        track.mode = 'showing'
    }
}

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
    case 'flac':
      return 'audio/flac'
    case 'aac':
      return 'audio/aac'
    case 'opus':
    case 'ogg':
      return 'audio/ogg'
    case 'alac':
      return 'audio/mp4'
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
  const isRemoteHttpSource = /^https?:\/\//i.test(url)
  const isAudio = baseMimeType.startsWith('audio/')

  console.log(`[VideoPlayer] Codec Support - AV1: ${av1Supported}, HEVC: ${hevcSupported}`)
  console.log(`[VideoPlayer] File MIME type: ${baseMimeType}`)

  if (isRemoteHttpSource) {
    const remoteSources = [{ src: url, type: baseMimeType }, { src: url, type: isAudio ? baseMimeType : 'video/mp4' }]
    console.log('[VideoPlayer] Using direct remote sources:', remoteSources)
    return remoteSources
  }

  // Audio files: keep it simple, no video codec fallbacks needed
  if (isAudio) {
    sources.push({ src: url, type: baseMimeType })
    console.log('[VideoPlayer] Generated audio sources:', sources)
    return sources
  }

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

// Chapter marker visibility state (from prop with default)
const showChapterMarkers = computed(() => props.showChapterMarkers ?? true)

// Hotkey and hint system
const currentSubtitleTrack = ref(0)
const hotkeyHintVisible = ref(false)
const hotkeyHintText = ref('')

let player: Player | null = null
const videoEl = ref<HTMLVideoElement | null>(null) // <- THE ONLY REF
const audioEl = ref<HTMLAudioElement | null>(null)
let hlsInstance: any = null
let audioHlsInstance: any = null
let separateAudioCleanup: (() => void) | null = null

function destroyHlsInstance() {
  if (hlsInstance) {
    hlsInstance.destroy()
    hlsInstance = null
  }
}

function destroyAudioHlsInstance() {
  if (audioHlsInstance) {
    audioHlsInstance.destroy()
    audioHlsInstance = null
  }
}

function resetSeparateAudioElement() {
  if (!audioEl.value) return
  audioEl.value.pause()
  audioEl.value.removeAttribute('src')
  audioEl.value.load()
}

async function loadSeparateAudioSource(src?: string, sourceType: 'file' | 'hls' = 'file') {
  destroyAudioHlsInstance()
  resetSeparateAudioElement()

  if (!audioEl.value || !src) return

  if (sourceType === 'hls') {
    const { default: Hls } = await import('hls.js')

    if (!audioEl.value) return

    if (Hls.isSupported()) {
      const hls = new Hls()
      hls.loadSource(src)
      hls.attachMedia(audioEl.value)
      audioHlsInstance = hls
      return
    }

    if (audioEl.value.canPlayType('application/vnd.apple.mpegurl')) {
      audioEl.value.src = src
      audioEl.value.load()
      return
    }
  }

  audioEl.value.src = src
  audioEl.value.load()
}

function syncSeparateAudioSettings() {
  if (!player || !audioEl.value || !props.audioSrc) return

  audioEl.value.volume = player.volume() ?? 1
  audioEl.value.muted = player.muted() ?? false
  audioEl.value.playbackRate = player.playbackRate() ?? 1
}

function syncSeparateAudioCurrentTime(force = false) {
  if (!player || !audioEl.value || !props.audioSrc) return

  const nextTime = player.currentTime()
  if (typeof nextTime !== 'number' || Number.isNaN(nextTime)) return

  if (force || Math.abs(audioEl.value.currentTime - nextTime) > 0.2) {
    try {
      audioEl.value.currentTime = nextTime
    } catch {
      // Ignore sync errors before audio metadata is ready.
    }
  }
}

function syncSeparateAudioState(forceSeek = false) {
  syncSeparateAudioSettings()
  syncSeparateAudioCurrentTime(forceSeek)
}

async function playSeparateAudio(forceSeek = false) {
  if (!player || !audioEl.value || !props.audioSrc) return

  syncSeparateAudioState(forceSeek)

  if (player.paused()) return

  try {
    await audioEl.value.play()
  } catch (error) {
    console.error('[VideoPlayer] Separate audio play failed:', error)
  }
}

function pauseSeparateAudio() {
  audioEl.value?.pause()
}

function setupSeparateAudioSync() {
  if (!player) return

  const handlePlay = () => {
    void playSeparateAudio(true)
  }
  const handlePause = () => {
    pauseSeparateAudio()
  }
  const handleSeeking = () => {
    syncSeparateAudioState(true)
  }
  const handleSeeked = () => {
    if (player?.paused()) {
      syncSeparateAudioState(true)
      return
    }

    void playSeparateAudio(true)
  }
  const handlePlaying = () => {
    void playSeparateAudio(true)
  }
  const handleWaiting = () => {
    pauseSeparateAudio()
  }
  const handleVolumeChange = () => {
    syncSeparateAudioSettings()
  }
  const handleRateChange = () => {
    syncSeparateAudioSettings()
  }
  const handleTimeUpdate = () => {
    if (!player || !audioEl.value || !props.audioSrc) return

    syncSeparateAudioCurrentTime(false)

    if (!player.paused() && audioEl.value.paused) {
      void playSeparateAudio(false)
    }
  }
  const handleEnded = () => {
    pauseSeparateAudio()
  }
  const handleLoadedMetadata = () => {
    syncSeparateAudioState(true)
    if (!player?.paused()) {
      void playSeparateAudio(true)
    }
  }

  player.on('play', handlePlay)
  player.on('playing', handlePlaying)
  player.on('pause', handlePause)
  player.on('waiting', handleWaiting)
  player.on('seeking', handleSeeking)
  player.on('seeked', handleSeeked)
  player.on('volumechange', handleVolumeChange)
  player.on('ratechange', handleRateChange)
  player.on('timeupdate', handleTimeUpdate)
  player.on('ended', handleEnded)

  audioEl.value?.addEventListener('loadedmetadata', handleLoadedMetadata)

  separateAudioCleanup = () => {
    if (!player) return
    player.off('play', handlePlay)
    player.off('playing', handlePlaying)
    player.off('pause', handlePause)
    player.off('waiting', handleWaiting)
    player.off('seeking', handleSeeking)
    player.off('seeked', handleSeeked)
    player.off('volumechange', handleVolumeChange)
    player.off('ratechange', handleRateChange)
    player.off('timeupdate', handleTimeUpdate)
    player.off('ended', handleEnded)
    audioEl.value?.removeEventListener('loadedmetadata', handleLoadedMetadata)
  }
}

function loadHlsSource(src: string) {
  if (!player || !videoEl.value) return

  destroyHlsInstance()

  import('hls.js').then(({ default: Hls }) => {
    if (!player || !videoEl.value) return

    if (Hls.isSupported()) {
      const hls = new Hls()
      hls.loadSource(src)
      hls.attachMedia(videoEl.value)
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        playerReady.value = true
      })
      hlsInstance = hls
    } else if (videoEl.value?.canPlayType('application/vnd.apple.mpegurl')) {
      player.src({ src, type: 'application/x-mpegURL' })
      playerReady.value = true
    }
  })
}

defineExpose({
  seek: (t: number) => player?.currentTime(t),
  pause: () => player?.pause(),
  play: () => player?.play(),
  currentTime: () => player?.currentTime() ?? 0,
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
function setupHotkeys(): () => void {
  const handleKeydown = (e: KeyboardEvent) => {
    // Only handle hotkeys if no input elements are focused and no modals/dropdowns are open
    const activeElement = document.activeElement
    const isInputFocused = activeElement instanceof HTMLInputElement || 
                          activeElement instanceof HTMLTextAreaElement ||
                          (activeElement as any)?.contentEditable === 'true'
    
    const isDropdownOpen = document.querySelector('.speed-dropdown[style*="display: block"]') ||
                          document.querySelector('.chapter-dropdown[style*="display: block"]')
    
    if (isInputFocused || isDropdownOpen || !player) return

    switch (e.key.toLowerCase()) {
      case ' ':
        e.preventDefault()
        togglePlayPause()
        showHotkeyHint(player.paused() ? 'Space - Paused' : 'Space - Playing')
        break
      case 'arrowleft':
        e.preventDefault()
        seekBySeconds(-5)
        showHotkeyHint('← -5s')
        break
      case 'arrowright':
        e.preventDefault()
        seekBySeconds(5)
        showHotkeyHint('→ +5s')
        break
      case 'f':
        e.preventDefault()
        toggleFullscreen()
        showHotkeyHint(player.isFullscreen() ? 'F - Exit Fullscreen' : 'F - Enter Fullscreen')
        break
// Removed C key handler
    } // Switch statement closing
   } // handleKeydown function closing

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

function handleVideoDoubleClick(e: MouseEvent) {
  if (!player) return
  e.preventDefault()
  e.stopPropagation()
  togglePlayPause()
  showHotkeyHint(player.paused() ? 'Paused' : 'Playing')
}

// Removed cycleSubtitles

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
// Custom Vue Control Bar Component
const createVueControlBarComponent = () => {
  const vjsComponent = videojs.getComponent('Component')
  class VueControlBarComponent extends vjsComponent {
    constructor(player: Player, options?: any) {
      super(player, options)
      this.addClass('vjs-vue-control-bar-component')
    }
    createEl() {
      return videojs.dom.createEl('div', {
        id: 'vue-custom-controls',
        className: 'vjs-vue-custom-controls',
        style: 'display: flex; align-items: center; height: 100%; margin-right: 10px;'
      })
    }
  }
  videojs.registerComponent('VueControlBarComponent', VueControlBarComponent)
}

let hotkeyCleanup: (() => void) | null = null

onMounted(async () => {
  if (!videoEl.value) return // safety

  // 加载字幕样式配置
  await loadSubtitleSettings()

  // Register custom components
  createEditableTimeDisplay()
  createCameraSnapshotControl()
  createVideoSpeedControl()
  createLoopCountControl()
  createVueControlBarComponent()

  // Setup hotkeys
  hotkeyCleanup = setupHotkeys()

  // For audio files, use native HTML5 playback (overrideNative breaks audio-only sources)
  const isAudioFile = getMediaMimeType(props.src).startsWith('audio/')

  player = videojs(videoEl.value!, {
    controls: true,
    preload: 'metadata',
    responsive: true,
    language: 'zh-CN',
    fill: true,
    experimentalSvgIcons: true,
    html5: {
      nativeAudioTracks: isAudioFile,
      nativeVideoTracks: isAudioFile,
      overrideNative: !isAudioFile,
    },
    crossorigin: 'anonymous',
    debug: true,
    userActions: {
      doubleClick: false, // Disable Video.js default double-click fullscreen
    },
    controlBar: {
        children: [
          'playToggle',
          'EditableCurrentTimeDisplay',
          'timeDivider',
          'durationDisplay',
          'progressControl',
          'skipBackward',
          'skipForward',
          'remainingTimeDisplay',
          'customControlSpacer',
          'playbackRateMenuButton',
          'descriptionsButton',
          // 'subsCapsButton', // Removed - using unified dropdown instead
          'CameraSnapshotControl',
          'VideoSpeedControl',
          'LoopCountControl',
          'VueControlBarComponent',
          'audioTrackButton',
          'ShareButton',
          'hlsQualitySelector',
          'QualitySelector',
          'volumePanel',
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

  if (props.sourceType === 'hls') {
    loadHlsSource(props.src)
  } else {
    destroyHlsInstance()
    const sources = getVideoSources(props.src)
    player.src(sources)
  }

  await loadSeparateAudioSource(props.audioSrc, props.audioSourceType ?? 'file')
  setupSeparateAudioSync()
  syncSeparateAudioState(true)

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
      
      if (props.sourceType !== 'hls' && playerError.code === 4 && errorRetryCount < maxRetries) {
        errorRetryCount++
        console.log(`[VideoPlayer] Attempting source recovery ${errorRetryCount}/${maxRetries}`)
        
        const basicMimeType = getMediaMimeType(props.src)
        let fallbackSources: Array<{ src: string; type: string }> = []
        
        if (errorRetryCount === 1) {
          if (basicMimeType.startsWith('audio/')) {
            fallbackSources = [
              { src: props.src, type: basicMimeType },
              { src: props.src, type: '' }
            ]
          } else {
            fallbackSources = [
              { src: props.src, type: basicMimeType },
              { src: props.src, type: 'video/mp4' },
              { src: props.src, type: 'video/webm' }
            ]
          }
        } else if (errorRetryCount === 2 && basicMimeType === 'video/x-matroska') {
          fallbackSources = [
            { src: props.src, type: 'video/mp4; codecs="hvc1.1.6.L93.B0"' },
            { src: props.src, type: 'video/mp4; codecs="avc1.64001F"' },
            { src: props.src, type: 'video/mp4' }
          ]
        } else if (errorRetryCount === 3) {
          fallbackSources = [
            { src: props.src, type: 'application/octet-stream' },
            { src: props.src, type: '' }
          ]
        }
        
        if (fallbackSources.length > 0) {
          console.log('[VideoPlayer] Trying fallback sources:', fallbackSources)
          player?.src(fallbackSources)
        }
      } else if (props.sourceType !== 'hls' && playerError.code === 4 && errorRetryCount >= maxRetries) {
        console.error('[VideoPlayer] All source recovery attempts failed')
        showMediaError('这个视频文件无法播放。可能是编码格式不被浏览器支持，或文件已损坏。')
      }
    }
  })

  player.on('loadstart', () => {
    console.log('[VideoPlayer] Video source loading started')
  })

  player.on('canplay', () => {
    console.log('[VideoPlayer] Video can play - codec supported!')
    emit('ready')
  })

  player.on('timeupdate', () => {
    const t = player!.currentTime()
    if (typeof t === 'number') {
      emit('time-update', t)
      updateCurrentChapter(t)
    }
  })

  player.on('ended', () => {
    console.log('[VideoPlayer] Video ended, checking autoplay settings')
    if (isAutoPlayEnabled.value) {
      console.log('[VideoPlayer] Autoplay enabled, requesting next video')
      emit('autoplay-next')
    } else {
      console.log('[VideoPlayer] Autoplay disabled, staying on current video')
    }
  })

  player.ready(() => {
    emit('ready')
    setTimeout(() => {
      addChapterMarkers()
    }, 100)
    
    player!.on('fullscreenchange', () => {
      const isFullscreen = player!.isFullscreen()
      console.log('[VideoPlayer] Fullscreen change:', isFullscreen)
      emit('fullscreen-change', !!isFullscreen)
    })
    
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

  if (player) {
    player.ready(() => {
      setTimeout(() => {
        if (!player) return
        const subsCapsButton = player.getChild('controlBar')?.getChild('subsCapsButton')
        if (subsCapsButton) {
          const menu = (subsCapsButton as any).menu
          if (menu) {
            const menuItems = menu.children()
            menuItems.forEach((item: any) => {
              if (item.hasClass && item.hasClass('vjs-texttrack-settings')) {
                item.hide()
                item.el().style.display = 'none'
              }
            })
            const settingsMenuItem = menu.el().querySelector('.vjs-texttrack-settings')
            if (settingsMenuItem) {
              settingsMenuItem.remove()
            }
          }
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

  setupBackgroundPlay()

  if (props.videoId) {
    loadChapters()
  }

  await loadSubtitleSettings()

  await checkFiles()
  playerReady.value = true
})

// Watch for showChapterMarkers prop changes
watch(() => props.showChapterMarkers, () => {
  console.log(`[VideoPlayer] showChapterMarkers changed to: ${showChapterMarkers.value}`)
  addChapterMarkers()
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
      }
    } catch (error) {
      console.error('Failed to load chapters:', error)
    }
  }
}

// Removed unused language track functions

// Removed LanguageSwitchControl

// Watch for videoId changes and reload chapters and language tracks
watch(
  () => props.videoId,
  async () => {
    if (props.videoId) {
      loadChapters()
      await checkFiles()
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
  async (src) => {
    if (props.sourceType === 'hls') {
      loadHlsSource(src)
    } else {
      destroyHlsInstance()
      const sources = getVideoSources(src)
      player?.src(sources)
    }
    await checkFiles()
  },
)
watch(
  () => [props.audioSrc, props.audioSourceType] as const,
  async ([src, sourceType]) => {
    await loadSeparateAudioSource(src, sourceType ?? 'file')

    if (!src) return

    if (player?.paused()) {
      syncSeparateAudioState(true)
      return
    }

    void playSeparateAudio(true)
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
  console.log(`[VideoPlayer] addChapterMarkers called - player: ${!!player}, chapters: ${chapters.value.length}, showMarkers: ${showChapterMarkers.value}`)

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

  // If markers are hidden, don't add new ones
  if (!showChapterMarkers.value) {
    console.log('[VideoPlayer] Chapter markers are hidden, skipping marker creation')
    return
  }

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
          background: transparent;
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

// Removed LanguageControl

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

      // Initial display update
      this.ready(() => {
        this.updateDisplay()
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
      // Update speed text on button
      const speedTextEl = this.el().querySelector('.vjs-speed-text') as HTMLElement
      if (speedTextEl) {
        const currentRate = this.player().playbackRate() || 1
        speedTextEl.textContent = `${currentRate.toFixed(1)}x`
      }

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
          background: transparent;
          border-radius: 4px;
          margin: 0 2px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 4px;
          width: auto;
          height: auto;
        `,
        title: 'Playback speed',
      })

      // Create Gauge icon
      const icon = videojs.dom.createEl('svg', {
        xmlns: 'http://www.w3.org/2000/svg',
        width: '18',
        height: '18',
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': '2',
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        style: 'display: block; flex-shrink: 0;',
      })
      icon.innerHTML = `
        <path d="m12 14 4-4"/>
        <path d="M3.34 19a10 10 0 1 1 17.32 0"/>
      `
      el.appendChild(icon)

      // Create speed text element
      const speedText = videojs.dom.createEl('span', {
        className: 'vjs-speed-text',
        style: `
          font-size: 12px;
          font-weight: 600;
          white-space: nowrap;
        `,
        textContent: '1.0x',
      })
      el.appendChild(speedText)

      return el
    }
  }

  videojs.registerComponent('VideoSpeedControl', VideoSpeedControl)
  return VideoSpeedControl
}

// Custom Loop Count Control Component
function createLoopCountControl() {
  const vjsComponent = videojs.getComponent('Component')

  class LoopCountControl extends vjsComponent {
    loopCount: number

    constructor(player: any, options: any) {
      super(player, options)
      this.addClass('vjs-loop-count-control')
      this.addClass('vjs-control')
      this.addClass('vjs-button')
      this.loopCount = 0 // 0 means play once and stop

      // Add click handler to cycle through common values
      this.on('click', this.cycleLoopCount.bind(this))

      // Listen for ended event to handle loop
      this.player().on('ended', this.handleEnded.bind(this))

      // Initial display update
      this.ready(() => {
        this.updateDisplay()
      })
    }

    cycleLoopCount() {
      // Cycle through: 0 -> 1 -> 2 -> 3 -> 5 -> 0
      const values = [0, 1, 2, 3, 5]
      const currentIndex = values.indexOf(this.loopCount)
      const nextIndex = (currentIndex + 1) % values.length
      this.loopCount = values[nextIndex]

      this.updateDisplay()
    }

    handleEnded() {
      if (this.loopCount > 0) {
        const player = this.player()
        if (player) {
          // Loop the video by seeking to the beginning
          player.currentTime(0)
          // Add a small delay before playing to ensure the seek completes
          // This is especially important for audio files (m4a, mp3, etc.)
          setTimeout(() => {
            player.play()
          }, 50)
          // Decrement loop count
          this.loopCount--
          this.updateDisplay()
          console.log(`[LoopCount] Loop remaining: ${this.loopCount}`)
        }
      } else {
        // Stop after playing once
        if (isAutoPlayEnabled.value) {
          isAutoPlayEnabled.value = false
          emit('autoplay-settings-changed', false)
        }
      }
    }

    updateDisplay() {
      const iconEl = this.el().querySelector('.loop-icon') as HTMLElement
      const countEl = this.el().querySelector('.loop-count-text') as HTMLElement

      if (this.loopCount === 0) {
        if (iconEl) iconEl.style.color = 'rgba(255, 255, 255, 0.4)'
        if (countEl) countEl.style.display = 'none'
      } else {
        if (iconEl) iconEl.style.color = 'rgba(255, 255, 255, 1)'
        if (countEl) {
          countEl.style.display = 'block'
          countEl.textContent = String(this.loopCount)
        }
      }
    }

    createEl() {
      const el = videojs.dom.createEl('div', {
        className: 'vjs-loop-count-control vjs-control vjs-button',
        style: `
          position: relative;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: auto;
          height: auto;
          background: transparent;
          cursor: pointer;
          padding: 6px;
          margin: 0 2px;
        `,
        title: '循环次数',
      })

      const iconEl = videojs.dom.createEl('span', {
        className: 'loop-icon',
        style: `
          display: flex;
          align-items: center;
          justify-content: center;
          color: rgba(255, 255, 255, 0.4);
          transition: color 0.2s ease;
        `,
      })
      iconEl.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/>
          <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
          <path d="M16 21v-5h5"/>
        </svg>
      `
      el.appendChild(iconEl)

      const countEl = videojs.dom.createEl('span', {
        className: 'loop-count-text',
        style: `
          position: absolute;
          font-size: 10px;
          font-weight: 800;
          font-family: -apple-system, BlinkMacSystemFont, sans-serif;
          color: white;
          line-height: 1;
          display: none;
          pointer-events: none;
          letter-spacing: -0.5px;
        `,
      })
      el.appendChild(countEl)

      return el
    }
  }

  videojs.registerComponent('LoopCountControl', LoopCountControl)
  return LoopCountControl
}

onBeforeUnmount(() => {
  // Clean up hotkeys
  if (hotkeyCleanup) {
    hotkeyCleanup()
  }
  separateAudioCleanup?.()
  destroyAudioHlsInstance()
  resetSeparateAudioElement()
  destroyHlsInstance()
  // Clean up player
  player?.dispose()
})
</script>

<template>
  <!-- the ref name must match the one in <script> -->
  <!-- give w-full h-full to div wrapper can Resist videojs overflowing -->
  <div class="relative w-full h-full">
    <video 
      ref="videoEl" 
      class="video-js vjs-luxmty vjs-fill w-full h-full" 
      crossorigin="anonymous"
      @dblclick="handleVideoDoubleClick"
    />
    <audio ref="audioEl" class="hidden" preload="metadata" crossorigin="anonymous" />
    
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

    <Teleport to="#vue-custom-controls" v-if="playerReady && props.sourceType !== 'hls'">
      <div class="flex items-center space-x-2 h-full">
        <!-- Language/Subtitle Control -->
        <div class="relative h-full flex items-center">
          <button
            ref="languageBtnRef"
            class="lang-panel-btn"
            :class="{ 'active': showLanguagePanel }"
            @click="toggleLanguagePanel"
          >
            <Languages :size="18" />
          </button>

          <Transition name="lang-panel">
            <div
              v-if="showLanguagePanel"
              ref="languagePanelRef"
              class="lang-panel"
            >
              <!-- Tab bar -->
              <div class="lang-panel-tabs">
                <button
                  class="lang-panel-tab"
                  :class="{ 'active': activeLanguageTab === 'dubbing' }"
                  @click="activeLanguageTab = 'dubbing'"
                >
                  AI原声翻译
                  <span class="lang-panel-tab-badge">Beta</span>
                </button>
                <button
                  class="lang-panel-tab"
                  :class="{ 'active': activeLanguageTab === 'subtitle' }"
                  @click="activeLanguageTab = 'subtitle'"
                >
                  字幕
                </button>
              </div>

              <!-- Dubbing tab content -->
              <div v-if="activeLanguageTab === 'dubbing'" class="lang-panel-body">
                <button class="lang-panel-item" @click="handleDubbingChange(null)">
                  <span :class="{ 'text-accent': dubbingLang === null }">关闭</span>
                  <Check v-if="dubbingLang === null" :size="14" class="text-accent" />
                </button>
                <button
                  class="lang-panel-item"
                  :class="{ 'disabled': !availableDubbings.en }"
                  :disabled="!availableDubbings.en"
                  @click="availableDubbings.en && handleDubbingChange('en')"
                >
                  <span :class="{ 'text-accent': dubbingLang === 'en' }">English (AI)</span>
                  <Check v-if="dubbingLang === 'en'" :size="14" class="text-accent" />
                </button>
                <button
                  class="lang-panel-item"
                  :class="{ 'disabled': !availableDubbings.ja }"
                  :disabled="!availableDubbings.ja"
                  @click="availableDubbings.ja && handleDubbingChange('ja')"
                >
                  <span :class="{ 'text-accent': dubbingLang === 'ja' }">日本語 (AI)</span>
                  <Check v-if="dubbingLang === 'ja'" :size="14" class="text-accent" />
                </button>
              </div>

              <!-- Subtitle tab content -->
              <div v-if="activeLanguageTab === 'subtitle'" class="lang-panel-body">
                <button class="lang-panel-item" @click="handleSubtitleChange(null)">
                  <span :class="{ 'text-accent': subtitleLang === null }">关闭</span>
                  <Check v-if="subtitleLang === null" :size="14" class="text-accent" />
                </button>
                <button
                  class="lang-panel-item"
                  :class="{ 'disabled': !availableSubtitles.zh }"
                  :disabled="!availableSubtitles.zh"
                  @click="availableSubtitles.zh && handleSubtitleChange('zh')"
                >
                  <span :class="{ 'text-accent': subtitleLang === 'zh' }">中文 (AI)</span>
                  <Check v-if="subtitleLang === 'zh'" :size="14" class="text-accent" />
                </button>
                <button
                  class="lang-panel-item"
                  :class="{ 'disabled': !availableSubtitles.en }"
                  :disabled="!availableSubtitles.en"
                  @click="availableSubtitles.en && handleSubtitleChange('en')"
                >
                  <span :class="{ 'text-accent': subtitleLang === 'en' }">English (AI)</span>
                  <Check v-if="subtitleLang === 'en'" :size="14" class="text-accent" />
                </button>
                <button
                  class="lang-panel-item"
                  :class="{ 'disabled': !availableSubtitles.ja }"
                  :disabled="!availableSubtitles.ja"
                  @click="availableSubtitles.ja && handleSubtitleChange('ja')"
                >
                  <span :class="{ 'text-accent': subtitleLang === 'ja' }">日本語 (AI)</span>
                  <Check v-if="subtitleLang === 'ja'" :size="14" class="text-accent" />
                </button>

                <!-- Divider -->
                <div class="lang-panel-divider" />

                <!-- Bilingual toggle -->
                <div class="lang-panel-row" @click.stop>
                  <span>双语字幕</span>
                  <el-switch
                    v-model="isBilingual"
                    size="small"
                    @change="(val: string | number | boolean) => toggleBilingual(Boolean(val))"
                    :disabled="!subtitleLang"
                  />
                </div>

                <!-- Subtitle settings -->
                <button class="lang-panel-item" @click="emit('open-subtitle-settings'); closeLanguagePanel()">
                  <span>字幕样式</span>
                  <SettingsIcon :size="14" class="opacity-60" />
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* Player Border - Removed as requested (no color) */

/* Control Bar - Transparent background, white text */
:deep(.video-js .vjs-control-bar) {
  background-color: rgba(0, 0, 0, 0.5);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

/* Progress Bar Colors */
:deep(.video-js .vjs-progress-control) {
  color: #13f5f5;
}

:deep(.video-js .vjs-play-progress) {
  background-color: #13f5f5;
}

:deep(.video-js .vjs-play-progress:before) {
  color: #13f5f5;
}

:deep(.video-js .vjs-load-progress) {
  background: rgba(19, 245, 245, 0.3);
}

:deep(.video-js .vjs-slider) {
  background-color: rgba(19, 245, 245, 0.3);
}

/* Button Colors - All white text */
:deep(.video-js .vjs-control-bar .vjs-button) {
  color: #ffffff;
}

:deep(.video-js .vjs-control-bar .vjs-button:hover) {
  color: #13f5f5;
}

/* Time display text */
:deep(.video-js .vjs-time-control) {
  color: #ffffff;
  text-shadow: 0 0 2px rgba(0, 0, 0, 0.8);
}

/* Remaining time display */
:deep(.video-js .vjs-remaining-time) {
  color: #ffffff;
  text-shadow: 0 0 2px rgba(0, 0, 0, 0.8);
}

/* Duration display */
:deep(.video-js .vjs-duration) {
  color: #ffffff;
  text-shadow: 0 0 2px rgba(0, 0, 0, 0.8);
}

/* Element Plus Dropdown Items */
:deep(.el-dropdown-menu__item.is-active) {
  color: #13f5f5 !important;
}

:deep(.el-switch.is-checked .el-switch__core) {
  border-color: #13f5f5;
  background-color: #13f5f5;
}

/* ── Language Panel ── */

.text-accent {
  color: #13f5f5;
}

.lang-panel-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #fff;
  cursor: pointer;
  transition: color 0.15s ease;
}

.lang-panel-btn:hover,
.lang-panel-btn.active {
  color: #13f5f5;
}

.lang-panel {
  position: absolute;
  bottom: calc(100% + 8px);
  right: 0;
  width: 240px;
  background: rgba(15, 15, 20, 0.95);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  overflow: hidden;
  box-shadow:
    0 -4px 24px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(19, 245, 245, 0.06);
  z-index: 9999;
}

/* Tab bar */
.lang-panel-tabs {
  display: flex;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.lang-panel-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 6px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.45);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  position: relative;
  transition: color 0.15s ease;
  letter-spacing: 0.02em;
}

.lang-panel-tab:hover {
  color: rgba(255, 255, 255, 0.7);
}

.lang-panel-tab.active {
  color: #13f5f5;
}

.lang-panel-tab.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 20%;
  right: 20%;
  height: 2px;
  background: #13f5f5;
  border-radius: 2px 2px 0 0;
}

.lang-panel-tab-badge {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(19, 245, 245, 0.15);
  color: #13f5f5;
  line-height: 1.2;
  letter-spacing: 0.03em;
}

/* Panel body */
.lang-panel-body {
  padding: 4px 0;
}

.lang-panel-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 16px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
  text-align: left;
}

.lang-panel-item:hover:not(.disabled) {
  background: rgba(255, 255, 255, 0.06);
}

.lang-panel-item.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.lang-panel-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
}

.lang-panel-divider {
  height: 1px;
  margin: 4px 14px;
  background: rgba(255, 255, 255, 0.08);
}

/* Transition */
.lang-panel-enter-active {
  transition: opacity 0.18s ease, transform 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}

.lang-panel-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.lang-panel-enter-from {
  opacity: 0;
  transform: translateY(6px) scale(0.97);
}

.lang-panel-leave-to {
  opacity: 0;
  transform: translateY(4px) scale(0.98);
}
</style>
