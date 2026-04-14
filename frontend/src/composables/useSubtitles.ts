import { ref, computed, watch } from 'vue'
import type { Ref } from 'vue'
import { getCSRFToken } from '@/composables/GetCSRFToken'
import { generateVTT } from '@/composables/Buildvtt'
import { ElMessage } from '@/composables/useNotification'
import type { Subtitle, SubtitleBilingual } from '@/types/subtitle'
import { markVideoDirty } from '@/composables/useVideoDirtyState'

// Subtitle management composable with editing state tracking
const _defaultrawSub: Subtitle[] = [
  {
    start: 0,
    end: 5,
    text: '欢迎来到Vue.js进阶教程',
  },
  {
    start: 5,
    end: 12,
    text: '今天我们将学习组合式API的核心概念',
  },
  {
    start: 12,
    end: 18,
    text: '首先让我们了解一下setup函数的基本用法',
  },
  {
    start: 18,
    end: 25,
    text: 'setup函数是组合式API的入口点',
  },
  {
    start: 25,
    end: 32,
    text: '在这里我们可以定义响应式数据和方法',
  },
  {
    start: 32,
    end: 40,
    text: '接下来我们看一个具体的例子',
  },
  {
    start: 40,
    end: 48,
    text: '使用ref函数可以创建响应式的引用',
  },
  {
    start: 48,
    end: 55,
    text: '这样我们就可以在模板中使用这些数据了',
  },
]

const _defaultforeignSub: Subtitle[] = [
  {
    start: 0,
    end: 5,
    text: 'Welcome to the advanced Vue.js tutorial',
  },
  {
    start: 5,
    end: 12,
    text: 'Today we will learn the core concepts of the Composition API',
  },
  {
    start: 12,
    end: 18,
    text: 'First, lets understand the basic usage of the setup function',
  },
  {
    start: 18,
    end: 25,
    text: 'The setup function is the entry point to the Composition API',
  },
  {
    start: 25,
    end: 32,
    text: 'Here we can define reactive data and methods',
  },
  {
    start: 32,
    end: 40,
    text: 'Next, lets look at a concrete example',
  },
  {
    start: 40,
    end: 48,
    text: 'Using the ref function, we can create reactive references',
  },
  {
    start: 48,
    end: 55,
    text: 'This way, we can use these data in the template',
  },
]

const subtitles = ref<Subtitle[]>(_defaultrawSub)
const subtitle2 = ref<Subtitle[]>(_defaultrawSub)

// Helper function to convert SubtitleBilingual array to reactive reference
function asRef(arr: SubtitleBilingual[] | null): Ref<SubtitleBilingual[]> {
  return computed(() => arr ?? [])
}

import { BACKEND } from '@/composables/ConfigAPI'

/** Parse SRT text into a fresh local Subtitle[] array (no shared state) */
function parseSRT(srt: string): Subtitle[] {
  const regex =
    /\d+\r?\n(\d{1,2}:\d{2}:\d{2}[.,]\d{3}) --> (\d{1,2}:\d{2}:\d{2}[.,]\d{3})\r?\n([\s\S]*?)(?=\r?\n\r?\n|\r?\n$)/g
  const result: Subtitle[] = []
  let match

  while ((match = regex.exec(srt)) !== null) {
    const timePartsStart = match[1].split(':')
    const secondsStart =
      +timePartsStart[0] * 3600 +
      +timePartsStart[1] * 60 +
      +parseFloat(timePartsStart[2].replace(/,/, '.'))

    const timePartsEnd = match[2].split(':')
    const secondsEnd =
      +timePartsEnd[0] * 3600 +
      +timePartsEnd[1] * 60 +
      +parseFloat(timePartsEnd[2].replace(/,/, '.'))

    result.push({
      start: secondsStart,
      end: secondsEnd,
      text: match[3].trim(),
    })
  }
  console.log('parsed subtitles:', result.length, 'items')
  return result
}

/** Serialize subtitles to SRT format (for download/upload) */
function serializeSRT(subs: Subtitle[]): string {
  let srtContent = ''
  subs.forEach((sub, index) => {
    srtContent += `${index + 1}\n${new Date(sub.start * 1000)
      .toISOString()
      .substr(11, 12)
      .replace('.', ',')} --> ${new Date(sub.end * 1000)
      .toISOString()
      .substr(11, 12)
      .replace('.', ',')}\n${sub.text}\n\n`
  })
  return srtContent
}

// // 下载字幕
// const downloadSubtitles = (subtitles:Subtitle[]) => {
//   const srtContent = serializeSRT(subtitles.values)

//   const link = document.createElement('a')
//   const blob = new Blob([srtContent], { type: 'text/plain;charset=utf-8' })
//   link.href = URL.createObjectURL(blob)
//   link.download = 'subtitles.srt'
//   link.click()
//   URL.revokeObjectURL(link.href)
// }

// Upload subtitles to database automatically
async function linkSubtitles(
  id: number, // Video ID
  lang: string = 'zh', // Subtitle language
  subs: Subtitle[],
): Promise<void> {
  const srtContent = serializeSRT(subs)
  const csrf = await getCSRFToken()
  const xhr = new XMLHttpRequest()
  const uploadUrl = `${BACKEND}/api/subtitle/upload/${id}?lang=${encodeURIComponent(lang)}`
  xhr.open('POST', uploadUrl, true)
  xhr.withCredentials = true
  xhr.setRequestHeader('Content-Type', 'application/json')
  xhr.setRequestHeader('X-CSRFToken', csrf)

  xhr.upload.onprogress = (event) => {
    if (event.lengthComputable) {
      const progress = (event.loaded / event.total) * 100
      console.log(`Subtitle upload Progress: ${progress.toFixed(2)}%`)
      const progressBar = document.getElementById('progress-bar')
      if (progressBar) {
        progressBar.style.width = `${progress}%`
      }
    }
  }

  xhr.onload = () => {
    if (xhr.status === 200 || xhr.status === 201) {
      try {
        const response = JSON.parse(xhr.responseText)
        if (response.success) {
          ElMessage.success('Subtitles successfully uploaded.')
          markVideoDirty(id)
        } else {
          ElMessage.error(response.message || 'Failed to upload subtitles.')
        }
      } catch (e) {
        ElMessage.error('Subtitles uploaded but invalid server response.')
      }
    } else {
      ElMessage.error(`Failed to upload subtitles. Status: ${xhr.status}`)
    }
  }

  xhr.onerror = () => {
    ElMessage.error('Network error occurred during subtitle upload.')
    console.error('Error uploading subtitles:', xhr.statusText)
  }
  // Send the serialized SRT content as JSON
  xhr.send(JSON.stringify({ srtContent }))
  return
}

async function fetchSubtitle(id: number, lang: string): Promise<Subtitle[]> {
  const res = await fetch(`${BACKEND}/api/subtitle/query/${id}?lang=${encodeURIComponent(lang)}`, {
    credentials: 'include',
  })
  if (!res.ok) {
    console.error('Subtitles load failed:', res.status, await res.text())
    throw new Error(`HTTP ${res.status}`)
  }
  const text = await res.text()
  // parseSRT now returns a fresh local Subtitle[] (no shared state)
  return parseSRT(text)
}

export function useSubtitles() {
  return {
    subtitles,
    parseSRT,
    serializeSRT,
    // downloadSubtitles,
    linkSubtitles,
    fetchSubtitle,
  }
}
