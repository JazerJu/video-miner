<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { markdownToHtml, processMarkdownContent } from '@/composables/ConvertMarkdown'
import { BACKEND } from '@/composables/ConfigAPI'
import { getCookie } from '@/composables/GetCSRFToken'
import { ElMessageBox } from 'element-plus'

const { t, locale } = useI18n()

const props = defineProps<{
  videoId: number
  filename: string
}>()

interface ToolStep {
  id: string
  name: string
  args: Record<string, unknown>
  status: 'running' | 'done' | 'error'
  summary?: string
  elapsedMs?: number
  open?: boolean
}

interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  renderedHtml?: string
  // 以下只用于 assistant：思考过程、工具调用轨迹、流式中的正文
  reasoning?: string
  steps?: ToolStep[]
  draft?: string
  phase?: 'thinking' | 'tools' | 'answering' | 'done' | 'error'
  showReasoning?: boolean
  isStreaming?: boolean
}

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isLoading = ref(false)
const showSummaryMenu = ref(false)
const isSubmittingSummary = ref(false)
const chatContainer = ref<HTMLElement | null>(null)
let msgCounter = 0

// 后端按 conversation_id 保存多轮上下文：每个聊天面板一份，点「新对话」换一个
const makeConversationId = () =>
  globalThis.crypto?.randomUUID?.() ?? `c${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
let conversationId = makeConversationId()
let activeReader: ReadableStreamDefaultReader<Uint8Array> | null = null

function newChat() {
  activeReader?.cancel().catch(() => {})
  messages.value = []
  conversationId = makeConversationId()
}

async function scrollToBottom() {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

async function renderMarkdown(msg: ChatMessage) {
  if (msg.role !== 'assistant') return
  msg.renderedHtml = await markdownToHtml(msg.content)
  await nextTick()
  const container = chatContainer.value
  if (container) {
    const el = container.querySelector(`[data-msg-id="${msg.id}"] .msg-html`)
    if (el) await processMarkdownContent(el as HTMLElement)
  }
}

function formatArgs(args: Record<string, unknown>) {
  return Object.entries(args || {})
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join('  ')
}

function applyEvent(msg: ChatMessage, event: any) {
  switch (event.type) {
    case 'reasoning_delta':
      msg.reasoning = (msg.reasoning || '') + event.text
      if (msg.phase !== 'answering') msg.phase = 'thinking'
      break
    case 'content_delta':
      msg.draft = (msg.draft || '') + event.text
      msg.phase = 'answering'
      break
    case 'tool_call':
      // 调工具之前模型说的话是过渡语，不算最终回答
      msg.draft = ''
      msg.steps = [
        ...(msg.steps || []),
        { id: event.id || `${event.name}-${msg.steps?.length || 0}`, name: event.name, args: event.args || {}, status: 'running' },
      ]
      msg.phase = 'tools'
      break
    case 'tool_result': {
      const steps = msg.steps || []
      const step =
        steps.find((s) => s.id === event.id) ||
        [...steps].reverse().find((s) => s.name === event.name && s.status === 'running')
      if (step) {
        step.status = event.ok === false ? 'error' : 'done'
        step.summary = event.summary
        step.elapsedMs = event.elapsed_ms
      }
      break
    }
    case 'finalizing':
      msg.phase = 'answering'
      break
    case 'answer':
      msg.content = event.content || msg.draft || ''
      msg.draft = ''
      msg.phase = 'done'
      msg.isStreaming = false
      msg.showReasoning = false
      break
    case 'error':
      msg.content = `${msg.content || msg.draft || ''}\n\nError: ${event.content}`.trim()
      msg.draft = ''
      msg.phase = 'error'
      msg.isStreaming = false
      break
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  messages.value.push({ id: ++msgCounter, role: 'user', content: text })
  inputText.value = ''
  messages.value.push({
    id: ++msgCounter,
    role: 'assistant',
    content: '',
    reasoning: '',
    steps: [],
    draft: '',
    phase: 'thinking',
    showReasoning: true,
    isStreaming: true,
  })
  // 从数组里取回响应式代理，后面直接改字段才会刷新界面
  const msg = messages.value[messages.value.length - 1]
  await scrollToBottom()
  isLoading.value = true

  try {
    const res = await fetch(`${BACKEND}/api/video-ask-stream/${encodeURIComponent(props.filename)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text, conversation_id: conversationId }),
    })
    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
      applyEvent(msg, { type: 'error', content: err.error || `HTTP ${res.status}` })
      return
    }

    const reader = res.body.getReader()
    activeReader = reader
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          applyEvent(msg, JSON.parse(line.slice(6)))
        } catch {
          // 半截或非 JSON 的行直接跳过
        }
      }
      await scrollToBottom()
    }
    if (msg.isStreaming) {
      // 流意外结束：已经收到的正文当回答保留
      applyEvent(msg, msg.draft ? { type: 'answer', content: msg.draft } : { type: 'error', content: 'stream ended' })
    }
    if (msg.phase === 'done') await renderMarkdown(msg)
  } catch (e: any) {
    if (msg.isStreaming) applyEvent(msg, { type: 'error', content: e.message || 'Unknown error' })
  } finally {
    activeReader = null
    isLoading.value = false
    await scrollToBottom()
  }
}

interface PrerequisitesResult {
  status: 'ok' | 'no_subtitles' | 'raw_lang_not_set' | 'video_not_found'
  video_id: number
  has_subtitles: boolean
  raw_lang: string | null
  available_langs: string[]
}

async function checkSummaryPrerequisites(): Promise<PrerequisitesResult | null> {
  try {
    const res = await fetch(`${BACKEND}/api/video-summary/${encodeURIComponent(props.filename)}/prerequisites`, {
      credentials: 'include',
    })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

async function generateSummary() {
  showSummaryMenu.value = false
  if (isSubmittingSummary.value) return

  const pre = await checkSummaryPrerequisites()
  if (!pre) {
    alert(t('vuSummaryFailed'))
    return
  }
  if (pre.status === 'no_subtitles') {
    alert(t('vuNeedSubtitles'))
    return
  }
  if (pre.status === 'raw_lang_not_set') {
    try {
      await ElMessageBox.confirm(
        t('vuBindRawLangPrompt'),
        t('vuBindRawLangTitle'),
        { confirmButtonText: t('vuBind'), cancelButtonText: t('vuCancel') }
      )
      const firstLang = pre.available_langs[0]
      const csrfToken = getCookie('csrftoken')
      const bindRes = await fetch(`${BACKEND}/api/videos/${pre.video_id}/update_raw_lang`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ raw_lang: firstLang }),
      })
      if (!bindRes.ok) {
        alert(t('vuBindRawLangFailed'))
        return
      }
    } catch {
      // user cancelled
      return
    }
  }

  isSubmittingSummary.value = true

  try {
    const csrfToken = getCookie('csrftoken')
    const res = await fetch(`${BACKEND}/api/summary/add`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify({ video_id: props.videoId, language: locale.value === 'zh' ? '中文' : 'English' }),
    })
    const data = await res.json()
    if (!res.ok) {
      alert(`${t('vuSummaryFailed')}: ${data.error || `HTTP ${res.status}`}`)
      return
    }
    // Task queued successfully - show hint
    const assistantMsg: ChatMessage = {
      id: ++msgCounter,
      role: 'assistant',
      content: t('vuSummarySubmitted'),
    }
    messages.value.push(assistantMsg)
    await scrollToBottom()
  } catch (e: any) {
    alert(`${t('vuSummaryFailed')}: ${e.message || 'Unknown error'}`)
  } finally {
    isSubmittingSummary.value = false
  }
}

async function openSummary() {
  showSummaryMenu.value = false

  const pre = await checkSummaryPrerequisites()
  if (!pre) {
    alert(t('vuSummaryFailed'))
    return
  }
  if (pre.status === 'no_subtitles') {
    alert(t('vuNeedSubtitles'))
    return
  }
  if (pre.status === 'raw_lang_not_set') {
    try {
      await ElMessageBox.confirm(
        t('vuBindRawLangPrompt'),
        t('vuBindRawLangTitle'),
        { confirmButtonText: t('vuBind'), cancelButtonText: t('vuCancel') }
      )
      const firstLang = pre.available_langs[0]
      const csrfToken = getCookie('csrftoken')
      const bindRes = await fetch(`${BACKEND}/api/videos/${pre.video_id}/update_raw_lang`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ raw_lang: firstLang }),
      })
      if (!bindRes.ok) {
        alert(t('vuBindRawLangFailed'))
        return
      }
    } catch {
      return
    }
  }

  const base = props.filename
  const url = `/summary/${base}`
  window.open(url, '_blank')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden relative">
    <!-- Chat Header -->
    <div class="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-slate-200 dark:border-slate-600/30">
      <span class="text-sm font-medium text-slate-600 dark:text-gray-300 pl-8">
        {{ t('videoQA') }}
      </span>
      <div class="flex items-center gap-2">
        <button
          v-if="messages.length"
          @click="newChat"
          class="px-3 py-1.5 text-xs rounded-md border border-slate-300 text-slate-600 hover:bg-slate-100 transition-colors dark:border-white/15 dark:text-gray-300 dark:hover:bg-white/10"
        >
          {{ t('vuNewChat') }}
        </button>
      <div class="relative">
        <button
          @click="showSummaryMenu = !showSummaryMenu"
          class="flex items-center gap-1 px-3 py-1.5 text-xs rounded-md border border-slate-300 text-slate-600 hover:bg-slate-100 transition-colors dark:border-white/15 dark:text-gray-300 dark:hover:bg-white/10"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          {{ t('vuSummary') }}
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        <div
          v-if="showSummaryMenu"
          class="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-50 min-w-[160px] overflow-hidden dark:bg-gray-800 dark:border-white/10"
        >
          <button
            @click="openSummary"
            class="w-full px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50 transition-colors dark:text-gray-200 dark:hover:bg-white/10"
          >
            {{ t('vuViewSummary') }}
          </button>
          <button
            @click="generateSummary"
            :disabled="isSubmittingSummary"
            class="w-full px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50 transition-colors dark:text-gray-200 dark:hover:bg-white/10 disabled:opacity-50"
          >
            {{ t('vuGenerateSummary') }}
          </button>
        </div>
      </div>
      </div>
    </div>

    <!-- Messages Area -->
    <div ref="chatContainer" class="flex-1 overflow-y-auto px-4 py-3 space-y-4 min-h-0">
      <!-- Empty State -->
      <div v-if="messages.length === 0" class="flex flex-col items-center justify-center h-full text-center space-y-3 py-8">
        <div class="w-14 h-14 bg-blue-500/10 rounded-full flex items-center justify-center">
          <svg class="h-7 w-7 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        </div>
        <p class="text-sm text-slate-400 dark:text-slate-500">{{ t('vuEmptyChat') }}</p>
      </div>

      <!-- Messages -->
      <template v-for="msg in messages" :key="msg.id">
        <!-- User Message -->
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <div class="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-br-md bg-blue-600 text-white text-sm whitespace-pre-wrap">
            {{ msg.content }}
          </div>
        </div>

        <!-- Assistant Message：思考过程 → 工具调用轨迹 → 回答 -->
        <div v-else class="flex justify-start">
          <div :data-msg-id="msg.id" class="w-full max-w-[92%] space-y-2">
            <div v-if="msg.reasoning" class="rounded-xl border border-slate-200 bg-slate-50/80 dark:border-white/10 dark:bg-white/5">
              <button
                type="button"
                @click="msg.showReasoning = !msg.showReasoning"
                class="flex w-full items-center gap-2 px-3 py-2 text-xs text-slate-500 dark:text-slate-400"
              >
                <span v-if="msg.phase === 'thinking'" class="h-2 w-2 shrink-0 rounded-full bg-teal-500 animate-pulse"></span>
                <span v-else class="h-2 w-2 shrink-0 rounded-full bg-slate-300 dark:bg-slate-500"></span>
                <span class="font-medium">{{ msg.phase === 'thinking' ? t('vuThinking') : t('vuReasoningDone', { n: msg.reasoning.length }) }}</span>
                <svg class="ml-auto h-3 w-3 transition-transform" :class="{ 'rotate-180': msg.showReasoning }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <div
                v-show="msg.showReasoning"
                class="max-h-56 overflow-y-auto whitespace-pre-wrap border-t border-slate-200 px-3 py-2 text-xs leading-relaxed text-slate-500 dark:border-white/10 dark:text-slate-400"
              >{{ msg.reasoning }}</div>
            </div>

            <div v-if="msg.steps && msg.steps.length" class="rounded-xl border border-slate-200 divide-y divide-slate-200 dark:border-white/10 dark:divide-white/10">
              <div class="px-3 py-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {{ t('vuToolSteps', { n: msg.steps.length }) }}
              </div>
              <div v-for="step in msg.steps" :key="step.id" class="px-3 py-2 text-xs">
                <button type="button" class="flex w-full items-center gap-2 text-left" @click="step.open = !step.open">
                  <span v-if="step.status === 'running'" class="h-3 w-3 shrink-0 rounded-full border-2 border-teal-500 border-t-transparent animate-spin"></span>
                  <span v-else-if="step.status === 'done'" class="shrink-0 text-teal-600 dark:text-teal-400">✓</span>
                  <span v-else class="shrink-0 text-red-500">✕</span>
                  <span class="shrink-0 font-mono font-medium text-slate-700 dark:text-slate-200">{{ step.name }}</span>
                  <span class="min-w-0 flex-1 truncate font-mono text-slate-400">{{ formatArgs(step.args) }}</span>
                  <span v-if="step.elapsedMs != null" class="shrink-0 text-slate-400">{{ (step.elapsedMs / 1000).toFixed(1) }}s</span>
                </button>
                <div
                  v-if="step.open && step.summary"
                  class="mt-1.5 max-h-40 overflow-y-auto whitespace-pre-wrap break-all rounded-md bg-slate-50 px-2 py-1.5 font-mono text-[11px] text-slate-500 dark:bg-white/5 dark:text-slate-400"
                >{{ step.summary }}</div>
              </div>
            </div>

            <div
              v-if="msg.content || msg.draft || msg.isStreaming"
              class="px-4 py-3 rounded-2xl rounded-bl-md bg-slate-100 text-slate-800 text-sm dark:bg-slate-700/50 dark:text-slate-200"
            >
              <div v-if="msg.renderedHtml" class="msg-html prose prose-sm max-w-none dark:prose-invert" v-html="msg.renderedHtml"></div>
              <div v-else-if="msg.content || msg.draft" class="whitespace-pre-wrap">{{ msg.content || msg.draft }}</div>
              <div v-if="msg.isStreaming" class="flex items-center gap-1" :class="{ 'mt-2': msg.content || msg.draft }">
                <span class="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                <span class="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                <span class="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Input Area -->
    <div class="flex-shrink-0 border-t border-slate-200 dark:border-slate-600/30 p-3">
      <div class="flex items-end gap-2">
        <textarea
          v-model="inputText"
          @keydown="handleKeydown"
          :placeholder="t('vuInputPlaceholder')"
          :disabled="isLoading"
          rows="1"
          class="flex-1 resize-none rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 disabled:opacity-50 dark:bg-slate-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-slate-500"
          @input="($event.target as HTMLTextAreaElement).style.height = 'auto'; ($event.target as HTMLTextAreaElement).style.height = ($event.target as HTMLTextAreaElement).scrollHeight + 'px'"
        ></textarea>
        <button
          @click="sendMessage"
          :disabled="!inputText.trim() || isLoading"
          class="flex-shrink-0 p-2.5 rounded-xl bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
