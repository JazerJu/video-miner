<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElButton, ElSelect, ElOption, ElSwitch, ElInput, ElIcon } from 'element-plus'
import { ElMessage } from '@/composables/useNotification'
import { Microphone, VideoPlay, VideoPause, Close } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

// Hypothesis Buffer implementation for smooth real-time transcription
class HypothesisBuffer {
  private commitedInBuffer: Array<[number, number, string]> = []
  private buffer: Array<[number, number, string]> = []
  private new: Array<[number, number, string]> = []
  private lastCommittedTime = 0
  private lastCommittedWord: string | null = null

  insert(newEntries: Array<[number, number, string]>, offset: number): void {
    // Add offset to timestamps
    newEntries = newEntries.map(([a, b, t]) => [a + offset, b + offset, t])

    // Filter entries that extend the committed buffer
    this.new = newEntries.filter(([a]) => a > this.lastCommittedTime - 0.1)

    if (this.new.length >= 1) {
      const [na, nb, nt] = this.new[0]
      if (Math.abs(na - this.lastCommittedTime) < 1) {
        if (this.commitedInBuffer.length > 0) {
          // Search for 1-5 consecutive words that are identical
          const cn = this.commitedInBuffer.length
          const nn = this.new.length
          for (let i = 1; i <= Math.min(Math.min(cn, nn), 5); i++) {
            const c = this.commitedInBuffer.slice(-i).map(([,, t]) => t).reverse().join(' ')
            const tail = this.new.slice(0, i).map(([,, t]) => t).join(' ')
            if (c === tail) {
              // Remove duplicate words
              this.new.splice(0, i)
              break
            }
          }
        }
      }
    }
  }

  flush(): Array<[number, number, string]> {
    const commit: Array<[number, number, string]> = []

    while (this.new.length > 0 && this.buffer.length > 0) {
      const [na, nb, nt] = this.new[0]
      const [ba, bb, bt] = this.buffer[0]

      if (nt === bt) {
        commit.push([na, nb, nt])
        this.lastCommittedWord = nt
        this.lastCommittedTime = nb
        this.buffer.shift()
        this.new.shift()
      } else {
        break
      }
    }

    this.buffer = [...this.new]
    this.new = []
    this.commitedInBuffer.push(...commit)

    return commit
  }

  popCommitted(time: number): void {
    while (this.commitedInBuffer.length > 0 && this.commitedInBuffer[0][1] <= time) {
      this.commitedInBuffer.shift()
    }
  }

  complete(): Array<[number, number, string]> {
    return this.buffer
  }
}

// Types
interface TranscriptionEntry {
  index: number
  start: string
  end: string
  text: string
  timestamp: number
}

interface KeywordEntry {
  id: string
  text: string
  timestamp: number
}

// Props
interface Props {
  modelValue: boolean
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

// Computed
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value)
})

// i18n
const { t } = useI18n()

// Recording state
const isRecording = ref(false)
const isPaused = ref(false)
const recordingDuration = ref(0)
const audioLevel = ref(0)

// Transcription state
const transcriptionEntries = ref<TranscriptionEntry[]>([])
const userTextInput = ref('')
const extractedKeywords = ref<string[]>([])
const autoSummary = ref(false)
const actionItems = ref(false)
const generatedTodos = ref<string[]>([])
const generatedMentions = ref<string[]>([])
const isProcessingText = ref(false)

// Language selection
const selectedLanguage = ref<'zh' | 'en'>('zh')

// Test audio file
const selectedAudioFile = ref<File | null>(null)
const audioElement = ref<HTMLAudioElement | null>(null)
const isTestMode = ref(false)
const isPlayingAudio = ref(false)
const audioUploadInput = ref<HTMLInputElement | null>(null)

// Media and WebSocket
let mediaRecorder: MediaRecorder | null = null
let audioContext: AudioContext | null = null
let analyser: AnalyserNode | null = null
let microphone: MediaStreamAudioSourceNode | null = null
let websocket: WebSocket | null = null
let stream: MediaStream | null = null

// Hypothesis buffer for smooth transcription
const hypothesisBuffer = ref(new HypothesisBuffer())

// Timer for recording duration
let durationTimer: number | null = null

// Audio level monitoring
let audioLevelTimer: number | null = null

// Computed properties
const formattedDuration = computed(() => {
  const minutes = Math.floor(recordingDuration.value / 60)
  const seconds = Math.floor(recordingDuration.value % 60)
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
})

const hasKeywords = computed(() => extractedKeywords.value.length > 0)
const hasGeneratedContent = computed(() => generatedTodos.value.length > 0 || generatedMentions.value.length > 0)

// Audio file upload handler
const handleAudioFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    // Check if file is audio
    if (!file.type.startsWith('audio/')) {
      ElMessage.error('请选择音频文件')
      return
    }

    selectedAudioFile.value = file
    isTestMode.value = true
    console.log(`Selected audio file: ${file.name}, size: ${file.size}, type: ${file.type}`)
  }
}

const clearAudioFile = () => {
  selectedAudioFile.value = null
  isTestMode.value = false
  isPlayingAudio.value = false
  if (audioUploadInput.value) {
    audioUploadInput.value.value = ''
  }
}

// Methods
const startRecording = async () => {
  try {
    if (isTestMode.value && selectedAudioFile.value) {
      // Test mode: play audio file
      await startAudioFileTest()
    } else {
      // Normal recording mode
      await startMicrophoneRecording()
    }
  } catch (error: any) {
    console.error('Error starting recording:', error)
    ElMessage.error('启动录音失败')
  }
}

const startAudioFileTest = async () => {
  if (!selectedAudioFile.value) {
    ElMessage.error('请先选择音频文件')
    return
  }

  try {
    // Cleanup previous audio context and element
    if (audioElement.value) {
      audioElement.value.pause()
      audioElement.value.src = ''
      audioElement.value = null
    }
    if (audioContext) {
      try {
        await audioContext.close()
      } catch (e) {
        console.log('AudioContext already closed:', e)
      }
      audioContext = null
    }

    // Setup WebSocket connection
    await connectWebSocket()

    // Create new audio element
    const audioUrl = URL.createObjectURL(selectedAudioFile.value)
    audioElement.value = new Audio(audioUrl)

    // Setup new audio context for capturing audio
    audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
    analyser = audioContext.createAnalyser()
    analyser.fftSize = 256

    // Create media stream from audio element
    const source = audioContext.createMediaElementSource(audioElement.value)
    const destination = audioContext.createMediaStreamDestination()

    // Connect audio element to both analyser and stream destination
    source.connect(analyser)
    source.connect(destination)
    source.connect(audioContext.destination) // Also play through speakers

    // Get the stream
    stream = destination.stream

    // Setup media recorder
    let mimeType = 'audio/webm;codecs=opus'
    const preferredFormats = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
      'audio/webm;codecs=vp8,opus'
    ]

    for (const format of preferredFormats) {
      if (MediaRecorder.isTypeSupported(format)) {
        mimeType = format
        console.log(`Using audio format: ${mimeType}`)
        break
      }
    }

    const options = { mimeType }
    mediaRecorder = new MediaRecorder(stream, options)
    mediaRecorder.ondataavailable = handleAudioData

    // Start recording and playing
    mediaRecorder.start(500)
    await audioElement.value.play()

    isRecording.value = true
    isPaused.value = false
    isPlayingAudio.value = true
    recordingDuration.value = 0

    startDurationTimer()
    startAudioLevelMonitoring()

    // Handle audio end
    audioElement.value.addEventListener('ended', () => {
      stopRecording()
      isPlayingAudio.value = false
    })

    // Handle audio error
    audioElement.value.addEventListener('error', (e) => {
      console.error('Audio element error:', e)
      ElMessage.error('音频播放失败')
      stopRecording()
    })

    ElMessage.success(`开始播放音频: ${selectedAudioFile.value.name}`)
    console.log(`Audio test started with file: ${selectedAudioFile.value.name}, format: ${mimeType}`)

  } catch (error: any) {
    console.error('Error starting audio test:', error)
    ElMessage.error(`音频播放测试失败: ${error.message}`)
  }
}

const startMicrophoneRecording = async () => {
  try {
    // Let the browser handle the permission request natively
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: { ideal: 16000 },
        channelCount: { ideal: 1 }  // Prefer mono for better transcription
      }
    })

    // Setup audio context for level monitoring
    audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
    analyser = audioContext.createAnalyser()
    analyser.fftSize = 256
    microphone = audioContext.createMediaStreamSource(stream)
    microphone.connect(analyser)

    // Setup media recorder with optimized settings for real-time transcription
    let mimeType = 'audio/webm;codecs=opus'

    // Try different formats in order of preference
    const preferredFormats = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
      'audio/webm;codecs=vp8,opus'
    ]

    for (const format of preferredFormats) {
      if (MediaRecorder.isTypeSupported(format)) {
        mimeType = format
        console.log(`Using audio format: ${mimeType}`)
        break
      }
    }

    const options = { mimeType }
    mediaRecorder = new MediaRecorder(stream, options)

    // Setup WebSocket connection
    await connectWebSocket()

    mediaRecorder.ondataavailable = handleAudioData

    // Use larger time slices for better audio chunks (500ms instead of 100ms)
    mediaRecorder.start(500)

    isRecording.value = true
    isPaused.value = false
    recordingDuration.value = 0

    startDurationTimer()
    startAudioLevelMonitoring()

    ElMessage.success('开始录音')
    console.log(`Recording started with format: ${mimeType}, language: ${selectedLanguage.value}`)
  } catch (error: any) {
    console.error('Error starting recording:', error)

    let errorMessage = '无法访问麦克风'

    if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
      errorMessage = '麦克风权限被拒绝，请在浏览器设置中允许麦克风访问'
    } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
      errorMessage = '未找到麦克风设备，请检查设备连接'
    } else if (error.name === 'NotSupportedError') {
      errorMessage = '浏览器不支持录音功能'
    } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
      errorMessage = '麦克风被其他应用占用，请关闭其他使用麦克风的应用'
    } else if (error.message) {
      errorMessage = error.message
    }

    ElMessage.error(errorMessage)
  }
}

const stopRecording = () => {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }

  if (stream) {
    stream.getTracks().forEach(track => track.stop())
    stream = null
  }

  if (audioElement.value) {
    audioElement.value.pause()
    audioElement.value.src = ''
    audioElement.value = null
  }

  if (audioContext) {
    try {
      audioContext.close()
    } catch (e) {
      console.log('AudioContext already closed:', e)
    }
    audioContext = null
  }

  if (websocket) {
    websocket.close()
    websocket = null
  }

  isRecording.value = false
  isPaused.value = false
  isPlayingAudio.value = false

  stopDurationTimer()
  stopAudioLevelMonitoring()

  ElMessage.success(isTestMode.value ? '音频播放已停止' : '录音已停止')
}

const pauseRecording = () => {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.pause()
    isPaused.value = true
    stopDurationTimer()
  }
}

const resumeRecording = () => {
  if (mediaRecorder && mediaRecorder.state === 'paused') {
    mediaRecorder.resume()
    isPaused.value = false
    startDurationTimer()
  }
}

const handleLanguageChange = () => {
  if (isRecording.value) {
    ElMessage.warning('更改语言将重新开始录音')
    stopRecording()
    setTimeout(() => {
      startRecording()
    }, 500)
  }
}

// Keyword extraction from user text
const extractKeywords = () => {
  if (!userTextInput.value.trim()) {
    extractedKeywords.value = []
    return
  }

  // Simple keyword extraction - split by common delimiters and filter out common words
  const text = userTextInput.value.toLowerCase()
  const words = text.split(/[,，、\s\n]+/)
    .map(word => word.replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, '')) // Keep only Chinese, English, and numbers
    .filter(word => word.length >= 2) // Filter out very short words

  // Remove common words (stop words)
  const stopWords = new Set([
    // Chinese stop words
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '这个', '那个',
    // English stop words
    'the', 'is', 'at', 'which', 'on', 'a', 'an', 'as', 'are', 'was', 'were', 'been', 'be', 'have', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now'
  ])

  const filteredWords = words.filter(word => !stopWords.has(word))

  // Get word frequency and sort by frequency
  const wordFreq = new Map<string, number>()
  filteredWords.forEach(word => {
    wordFreq.set(word, (wordFreq.get(word) || 0) + 1)
  })

  // Sort by frequency and take top 10 keywords
  const sortedWords = Array.from(wordFreq.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([word]) => word)

  extractedKeywords.value = sortedWords
}

// Generate todos and mentions from user text and transcription using LLM
const generateTodosAndMentions = async () => {
  if (!userTextInput.value.trim() && transcriptionEntries.value.length === 0) {
    ElMessage.warning('请先输入文本或进行录音转录')
    return
  }

  isProcessingText.value = true

  try {
    // Combine user text and transcription text
    const allText = [
      userTextInput.value,
      ...transcriptionEntries.value.map(entry => entry.text)
    ].join('\n')

    console.log(`[Extract Insights] Sending ${allText.length} chars to LLM...`)

    // Call backend API for intelligent extraction
    const response = await fetch('/api/extract_insights', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text: allText,
        language: selectedLanguage.value
      })
    })

    const result = await response.json()

    if (result.success) {
      generatedTodos.value = result.data.todos || []
      generatedMentions.value = result.data.mentions || []

      console.log(`[Extract Insights] Extracted ${generatedTodos.value.length} todos and ${generatedMentions.value.length} mentions`)
      ElMessage.success(`生成完成: ${generatedTodos.value.length}条待办事项, ${generatedMentions.value.length}条关键要点`)
    } else {
      throw new Error(result.error || '提取失败')
    }
  } catch (error: any) {
    console.error('Error generating content:', error)
    ElMessage.error(`生成失败: ${error.message || '请重试'}`)
  } finally {
    isProcessingText.value = false
  }
}

const clearGeneratedContent = () => {
  generatedTodos.value = []
  generatedMentions.value = []
}

const clearAllTranscription = () => {
  transcriptionEntries.value = []
}

const connectWebSocket = async () => {
  try {
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/realtime-transcription/`
    websocket = new WebSocket(wsUrl)

    websocket.onopen = () => {
      console.log('WebSocket connected')
      // Send language preference
      websocket?.send(JSON.stringify({
        type: 'start',
        language: selectedLanguage.value
      }))
    }

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleTranscriptionData(data)
    }

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error)
      ElMessage.error('连接服务器失败，请重试')
    }

    websocket.onclose = () => {
      console.log('WebSocket disconnected')
    }
  } catch (error) {
    console.error('Error connecting WebSocket:', error)
    ElMessage.error('无法连接到转录服务')
  }
}

const handleAudioData = (event: BlobEvent) => {
  if (event.data.size > 0 && websocket && websocket.readyState === WebSocket.OPEN) {
    // Log audio data size for debugging
    console.log(`Sending audio chunk: ${event.data.size} bytes, type: ${event.data.type}`)

    // Convert blob to array buffer and send via WebSocket
    event.data.arrayBuffer().then(buffer => {
      if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(buffer)
        console.log(`Sent audio buffer: ${buffer.byteLength} bytes`)
      }
    }).catch(error => {
      console.error('Error processing audio data:', error)
    })
  } else {
    console.warn(`Cannot send audio: size=${event.data.size}, websocket ready=${websocket?.readyState}`)
  }
}

const handleTranscriptionData = (data: any) => {
  if (data.type === 'transcription' && data.entries) {
    // Process new transcription entries
    const newEntries: TranscriptionEntry[] = data.entries.map((entry: any, index: number) => ({
      index: transcriptionEntries.value.length + index + 1,
      start: entry.start,
      end: entry.end,
      text: entry.text,
      timestamp: Date.now()
    }))

    transcriptionEntries.value.push(...newEntries)

    // Auto-scroll to bottom
    nextTick(() => {
      const container = document.querySelector('.transcription-container')
      if (container) {
        container.scrollTop = container.scrollHeight
      }
    })
  }
}

const startDurationTimer = () => {
  durationTimer = window.setInterval(() => {
    recordingDuration.value++
  }, 1000)
}

const stopDurationTimer = () => {
  if (durationTimer) {
    clearInterval(durationTimer)
    durationTimer = null
  }
}

const startAudioLevelMonitoring = () => {
  const updateAudioLevel = () => {
    if (analyser) {
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      analyser.getByteFrequencyData(dataArray)

      // Calculate average audio level
      const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length
      audioLevel.value = Math.min(100, (average / 128) * 100)
    }

    if (isRecording.value && !isPaused.value) {
      audioLevelTimer = requestAnimationFrame(updateAudioLevel)
    }
  }

  updateAudioLevel()
}

const stopAudioLevelMonitoring = () => {
  if (audioLevelTimer) {
    cancelAnimationFrame(audioLevelTimer)
    audioLevelTimer = null
  }
  audioLevel.value = 0
}

const highlightKeywords = (text: string): string => {
  let highlightedText = text

  extractedKeywords.value.forEach(keyword => {
    const regex = new RegExp(`(${keyword})`, 'gi')
    highlightedText = highlightedText.replace(regex, '<mark class="bg-yellow-300 text-yellow-900 px-1 rounded">$1</mark>')
  })

  return highlightedText
}

// Lifecycle
onMounted(() => {
  // Check browser support
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    // Check if the issue is likely due to insecure context (HTTP vs HTTPS)
    const isSecureContext = window.isSecureContext || 
                           window.location.protocol === 'https:' || 
                           window.location.hostname === 'localhost' || 
                           window.location.hostname === '127.0.0.1';
    
    if (!isSecureContext) {
      ElMessage.error('录音功能仅在HTTPS或本地环境(localhost)下可用')
    } else {
      ElMessage.error('您的浏览器不支持录音功能')
    }
    return
  }
})

onBeforeUnmount(() => {
  if (isRecording.value) {
    stopRecording()
  }
})
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    @click.self="visible = false"
  >
    <div class="bg-white rounded-xl shadow-2xl w-[90vw] h-[85vh] max-w-7xl flex overflow-hidden">
      <!-- Left Panel - Key Points -->
      <div class="w-2/5 bg-gray-50 border-r border-gray-200 flex flex-col">
        <!-- Header -->
        <div class="p-4 border-b border-gray-200 bg-white">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold text-gray-800">关键要点</h2>
            <el-button
              type="text"
              @click="visible = false"
              class="text-gray-400 hover:text-gray-600"
            >
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </div>

        <!-- User Text Input -->
        <div class="flex-1 flex flex-col">
          <div class="p-4 border-b border-gray-200 bg-white">
            <div class="space-y-3">
              <label class="block text-sm font-medium text-gray-700">文本输入</label>
              <el-input
                v-model="userTextInput"
                type="textarea"
                :rows="8"
                placeholder="在此输入您的想法、会议要点或任何内容..."
                @input="extractKeywords"
                class="w-full"
              />

              <!-- Extracted Keywords -->
              <div v-if="hasKeywords" class="mt-3">
                <h4 class="text-sm font-medium text-gray-700 mb-2">提取的关键词：</h4>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="keyword in extractedKeywords"
                    :key="keyword"
                    class="inline-flex items-center px-2 py-1 bg-blue-100 text-blue-800 text-xs font-medium rounded-full"
                  >
                    {{ keyword }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Action Buttons -->
          <div class="p-4 border-b border-gray-200 bg-white">
            <div class="space-y-3">
              <el-button
                @click="generateTodosAndMentions"
                type="primary"
                :loading="isProcessingText"
                :disabled="!userTextInput.trim() && transcriptionEntries.length === 0"
                class="w-full !bg-green-600 !border-green-600 hover:!bg-green-700"
              >
                <el-icon class="mr-2">
                  <Microphone />
                </el-icon>
                生成待办事项和提及
              </el-button>

              <div class="flex items-center justify-between text-sm">
                <div class="flex items-center gap-2">
                  <el-switch v-model="autoSummary" size="small" />
                  <span class="text-gray-700">包含摘要</span>
                </div>
                <div class="flex items-center gap-2">
                  <el-switch v-model="actionItems" size="small" />
                  <span class="text-gray-700">包含行动项目</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Generated Content -->
          <div class="flex-1 p-4 overflow-y-auto">
            <div v-if="hasGeneratedContent" class="space-y-4">
              <!-- Todos -->
              <div v-if="generatedTodos.length > 0">
                <h4 class="text-sm font-medium text-gray-700 mb-2 flex items-center">
                  <span class="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                  待办事项 ({{ generatedTodos.length }})
                </h4>
                <div class="space-y-2">
                  <div
                    v-for="(todo, index) in generatedTodos"
                    :key="index"
                    class="p-2 bg-green-50 rounded-lg border border-green-200 text-sm text-green-800"
                  >
                    {{ todo }}
                  </div>
                </div>
              </div>

              <!-- Mentions -->
              <div v-if="generatedMentions.length > 0">
                <h4 class="text-sm font-medium text-gray-700 mb-2 flex items-center">
                  <span class="w-2 h-2 bg-purple-500 rounded-full mr-2"></span>
                  提及 ({{ generatedMentions.length }})
                </h4>
                <div class="space-y-2">
                  <div
                    v-for="(mention, index) in generatedMentions"
                    :key="index"
                    class="p-2 bg-purple-50 rounded-lg border border-purple-200 text-sm text-purple-800"
                  >
                    {{ mention }}
                  </div>
                </div>
              </div>

              <!-- Clear Button -->
              <el-button
                @click="clearGeneratedContent"
                size="small"
                type="info"
                plain
                class="w-full"
              >
                清空生成内容
              </el-button>
            </div>

            <div v-else class="text-center text-gray-500 py-8">
              <el-icon size="48" class="text-gray-300 mb-4">
                <Microphone />
              </el-icon>
              <p>暂无生成内容</p>
              <p class="text-sm mt-1">输入文本或进行录音后点击"生成待办事项和提及"</p>
            </div>
          </div>
        </div>

        <!-- Recording Info -->
        <div class="p-4 border-t border-gray-200 bg-white">
          <div class="space-y-2">
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">录音时长</span>
              <span class="font-mono text-gray-800">{{ formattedDuration }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">音频电平</span>
              <div class="flex items-center gap-2">
                <div class="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-green-500 transition-all duration-100"
                    :style="{ width: `${audioLevel}%` }"
                  />
                </div>
                <span class="text-gray-800">{{ Math.round(audioLevel) }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Panel - Transcription -->
      <div class="flex-1 flex flex-col">
        <!-- Header -->
        <div class="p-4 border-b border-gray-200 bg-white">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold text-gray-800">实时转录</h2>
            <div class="flex items-center gap-3">
              <!-- Language Selector -->
              <el-select
                v-model="selectedLanguage"
                @change="handleLanguageChange"
                class="w-24"
                size="small"
              >
                <el-option label="中文" value="zh" />
                <el-option label="English" value="en" />
              </el-select>

              <!-- Clear Button -->
              <el-button
                @click="clearAllTranscription"
                size="small"
                type="info"
                plain
              >
                清空
              </el-button>
            </div>
          </div>
        </div>

        <!-- Transcription Display -->
        <div class="flex-1 p-4 overflow-y-auto transcription-container bg-gray-50">
          <div v-if="transcriptionEntries.length === 0" class="text-center text-gray-500 py-12">
            <el-icon size="48" class="text-gray-300 mb-4">
              <Microphone />
            </el-icon>
            <p class="text-lg">点击"开始录音"开始实时转录</p>
            <p class="text-sm mt-1">转录内容将在此处实时显示</p>
          </div>

          <div v-else class="space-y-3">
            <div
              v-for="entry in transcriptionEntries"
              :key="entry.index"
              class="p-3 bg-white rounded-lg border border-gray-200 shadow-sm"
            >
              <div class="flex items-start gap-3">
                <div class="flex-shrink-0">
                  <span class="inline-flex items-center justify-center w-6 h-6 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">
                    {{ entry.index }}
                  </span>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="text-xs text-gray-500 mb-1">
                    {{ entry.start }} - {{ entry.end }}
                  </div>
                  <div
                    class="text-gray-800 leading-relaxed"
                    v-html="highlightKeywords(entry.text)"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Recording Controls -->
        <div class="p-4 border-t border-gray-200 bg-white">
          <!-- Audio File Upload Section -->
          <div class="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-sm font-medium text-blue-800">音频文件测试</h3>
              <div class="flex items-center gap-2">
                <el-switch
                  v-model="isTestMode"
                  size="small"
                  active-text="测试模式"
                  inactive-text="录音模式"
                />
              </div>
            </div>

            <div v-if="isTestMode" class="space-y-3">
              <div class="flex items-center gap-3">
                <input
                  ref="audioUploadInput"
                  type="file"
                  accept="audio/*"
                  @change="handleAudioFileSelect"
                  class="hidden"
                />
                <el-button
                  @click="audioUploadInput?.click()"
                  size="small"
                  type="primary"
                  plain
                >
                  <el-icon class="mr-2">
                    <Microphone />
                  </el-icon>
                  选择音频文件
                </el-button>

                <el-button
                  v-if="selectedAudioFile"
                  @click="clearAudioFile"
                  size="small"
                  type="danger"
                  plain
                >
                  清除
                </el-button>
              </div>

              <div v-if="selectedAudioFile" class="text-xs text-blue-700">
                <div class="flex items-center justify-between">
                  <span class="font-medium">已选择:</span>
                  <span>{{ selectedAudioFile.name }}</span>
                </div>
                <div class="flex items-center justify-between">
                  <span>大小:</span>
                  <span>{{ (selectedAudioFile.size / 1024 / 1024).toFixed(2) }} MB</span>
                </div>
                <div class="flex items-center justify-between">
                  <span>类型:</span>
                  <span>{{ selectedAudioFile.type }}</span>
                </div>
              </div>

              <div v-else class="text-xs text-blue-600 italic">
                请选择音频文件进行转录测试
              </div>
            </div>
          </div>

          <div class="flex items-center justify-center gap-4">
            <!-- Main Record/Stop Button -->
            <el-button
              v-if="!isRecording"
              @click="startRecording"
              type="primary"
              size="large"
              :class="isTestMode ? '!bg-blue-600 !border-blue-600 hover:!bg-blue-700' : '!bg-red-600 !border-red-600 hover:!bg-red-700'"
              :disabled="isTestMode && !selectedAudioFile"
              class="!px-8 !py-3"
            >
              <el-icon class="mr-2">
                <Microphone />
              </el-icon>
              {{ isTestMode ? '播放音频测试' : '开始录音' }}
            </el-button>

            <el-button
              v-else
              @click="stopRecording"
              type="danger"
              size="large"
              class="!bg-gray-600 !border-gray-600 hover:!bg-gray-700 !px-8 !py-3"
            >
              <el-icon class="mr-2">
                <Close />
              </el-icon>
              {{ isTestMode ? '停止播放' : '停止录音' }}
            </el-button>

            <!-- Pause/Resume Button -->
            <el-button
              v-if="isRecording && !isPaused"
              @click="pauseRecording"
              type="warning"
              size="large"
              class="!px-6 !py-3"
            >
              <el-icon class="mr-2">
                <VideoPause />
              </el-icon>
              暂停
            </el-button>

            <el-button
              v-if="isRecording && isPaused"
              @click="resumeRecording"
              type="success"
              size="large"
              class="!px-6 !py-3"
            >
              <el-icon class="mr-2">
                <VideoPlay />
              </el-icon>
              继续
            </el-button>
          </div>

          <!-- Recording Status -->
          <div v-if="isRecording" class="mt-3 text-center">
            <span
              :class="[
                'inline-flex items-center px-3 py-1 rounded-full text-xs font-medium',
                isPaused
                  ? 'bg-yellow-100 text-yellow-800'
                  : isTestMode
                    ? 'bg-blue-100 text-blue-800 animate-pulse'
                    : 'bg-red-100 text-red-800 animate-pulse'
              ]"
            >
              <span
                :class="[
                  'w-2 h-2 rounded-full mr-2',
                  isPaused ? 'bg-yellow-500' : isTestMode ? 'bg-blue-500' : 'bg-red-500'
                ]"
              />
              <span v-if="isTestMode && isPlayingAudio">播放中</span>
              <span v-else-if="isTestMode">测试中</span>
              <span v-else-if="isPaused">已暂停</span>
              <span v-else>录音中</span>
              - {{ formattedDuration }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.transcription-container {
  max-height: calc(85vh - 200px);
}

/* Custom scrollbar styling */
.transcription-container::-webkit-scrollbar {
  width: 6px;
}

.transcription-container::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.transcription-container::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.transcription-container::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

/* Keyword highlight styling */
:deep(mark) {
  background-color: #fef08a;
  color: #713f12;
  padding: 1px 4px;
  border-radius: 4px;
  font-weight: 500;
}

/* Recording status animation */
@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>