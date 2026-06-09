<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { markdownToHtml, processMarkdownContent } from '@/composables/ConvertMarkdown'
import { BACKEND } from '@/composables/ConfigAPI'
import { getCookie } from '@/composables/GetCSRFToken'

const { t, locale } = useI18n()

const props = defineProps<{
  videoId: number
  filename: string
}>()

interface ChatMessage {
  id: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  renderedHtml?: string
  toolName?: string
  isStreaming?: boolean
}

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isLoading = ref(false)
const showSummaryMenu = ref(false)
const isSubmittingSummary = ref(false)
const chatContainer = ref<HTMLElement | null>(null)
let msgCounter = 0

async function scrollToBottom() {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

async function renderMarkdown(msg: ChatMessage) {
  if (msg.role === 'user' || msg.role === 'tool') return
  msg.renderedHtml = await markdownToHtml(msg.content)
  await nextTick()
  const container = chatContainer.value
  if (container) {
    const el = container.querySelector(`[data-msg-id="${msg.id}"] .msg-html`)
    if (el) await processMarkdownContent(el as HTMLElement)
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  const userMsg: ChatMessage = { id: ++msgCounter, role: 'user', content: text }
  messages.value.push(userMsg)
  inputText.value = ''
  await scrollToBottom()

  isLoading.value = true

  const toolMsg: ChatMessage = {
    id: ++msgCounter,
    role: 'tool',
    content: '',
    toolName: t('vuToolCalling'),
  }
  messages.value.push(toolMsg)
  await scrollToBottom()

  try {
    const res = await fetch(`${BACKEND}/api/video-ask/${encodeURIComponent(props.filename)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text }),
    })

    const toolIdx = messages.value.findIndex((m) => m.id === toolMsg.id)
    if (toolIdx !== -1) messages.value.splice(toolIdx, 1)

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
      const assistantMsg: ChatMessage = {
        id: ++msgCounter,
        role: 'assistant',
        content: `Error: ${err.error || `HTTP ${res.status}`}`,
      }
      messages.value.push(assistantMsg)
      await scrollToBottom()
      return
    }

    const data = await res.json()
    const assistantMsg: ChatMessage = {
      id: ++msgCounter,
      role: 'assistant',
      content: data.answer,
      isStreaming: true,
    }
    messages.value.push(assistantMsg)
    await scrollToBottom()
    await renderMarkdown(assistantMsg)
    assistantMsg.isStreaming = false
  } catch (e: any) {
    const toolIdx = messages.value.findIndex((m) => m.id === toolMsg.id)
    if (toolIdx !== -1) messages.value.splice(toolIdx, 1)

    const assistantMsg: ChatMessage = {
      id: ++msgCounter,
      role: 'assistant',
      content: `Error: ${e.message || 'Unknown error'}`,
    }
    messages.value.push(assistantMsg)
    await scrollToBottom()
  } finally {
    isLoading.value = false
  }
}

async function generateSummary() {
  showSummaryMenu.value = false
  if (isSubmittingSummary.value) return
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

function openSummary() {
  const base = props.filename
  const url = `/summary/${base}`
  window.open(url, '_blank')
  showSummaryMenu.value = false
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

        <!-- Assistant Message -->
        <div v-else-if="msg.role === 'assistant'" class="flex justify-start">
          <div
            :data-msg-id="msg.id"
            class="max-w-[85%] px-4 py-3 rounded-2xl rounded-bl-md bg-slate-100 text-slate-800 text-sm dark:bg-slate-700/50 dark:text-slate-200"
          >
            <div v-if="msg.renderedHtml" class="msg-html prose prose-sm max-w-none dark:prose-invert" v-html="msg.renderedHtml"></div>
            <div v-else class="whitespace-pre-wrap">{{ msg.content }}</div>
            <div v-if="msg.isStreaming" class="flex items-center gap-1 mt-2">
              <span class="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
              <span class="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
              <span class="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
            </div>
          </div>
        </div>

        <!-- Tool Call Indicator -->
        <div v-else-if="msg.role === 'tool'" class="flex justify-start">
          <div class="flex items-center gap-2 px-4 py-2 rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 dark:border-slate-500 dark:bg-slate-800/30">
            <div class="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin"></div>
            <span class="text-xs text-slate-500 dark:text-slate-400">{{ msg.toolName }}</span>
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
