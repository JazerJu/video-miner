<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { markdownToHtml, processMarkdownContent } from '@/composables/ConvertMarkdown'
import { BACKEND } from '@/composables/ConfigAPI'

const route = useRoute()
const router = useRouter()
const pathSegments = route.path.replace('/summary/', '').split('.')
const filename = pathSegments.length > 1 ? `${pathSegments.slice(0, -1).join('.')}.${pathSegments[pathSegments.length - 1]}` : route.path.replace('/summary/', '')

const loading = ref(true)
const error = ref('')
const renderedHtml = ref('')
const containerRef = ref<HTMLElement | null>(null)

const isEditing = ref(false)
const editContent = ref('')
const rawMarkdown = ref('')
const saving = ref(false)

async function renderMarkdown(mdContent: string) {
  renderedHtml.value = await markdownToHtml(mdContent)
  if (containerRef.value) await processMarkdownContent(containerRef.value)
}

onMounted(async () => {
  try {
    const res = await fetch(`${BACKEND}/api/video-summary/${encodeURIComponent(filename)}`, {
      credentials: 'include',
    })
    if (!res.ok) {
      if (res.status === 404) {
        await checkPrerequisitesAndShowError()
      } else {
        error.value = `Failed to load summary (${res.status})`
      }
      return
    }
    const data = await res.json()
    const mdContent = data.summary || data.content || ''
    if (!mdContent) {
      await checkPrerequisitesAndShowError()
      return
    }
    rawMarkdown.value = mdContent
    await renderMarkdown(mdContent)
  } catch (err) {
    error.value = 'Failed to load summary.'
  } finally {
    loading.value = false
  }
})

async function checkPrerequisitesAndShowError() {
  try {
    const preRes = await fetch(`${BACKEND}/api/video-summary/${encodeURIComponent(filename)}/prerequisites`, {
      credentials: 'include',
    })
    if (preRes.ok) {
      const pre = await preRes.json()
      if (pre.status === 'no_subtitles') {
        error.value = 'Subtitles required. Please generate subtitles for this video first.'
        return
      }
      if (pre.status === 'raw_lang_not_set') {
        error.value = 'Subtitles exist but video language is not bound. Please set the video language in settings.'
        return
      }
    }
  } catch {}
  error.value = 'Summary not available yet.'
}

function startEdit() {
  editContent.value = rawMarkdown.value
  isEditing.value = true
}

function cancelEdit() {
  isEditing.value = false
}

async function saveEdit() {
  saving.value = true
  try {
    const res = await fetch(`${BACKEND}/api/video-summary/${encodeURIComponent(filename)}`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ summary: editContent.value }),
    })
    if (!res.ok) {
      error.value = `Failed to save (${res.status})`
      return
    }
    rawMarkdown.value = editContent.value
    await renderMarkdown(editContent.value)
    isEditing.value = false
  } catch (err) {
    error.value = 'Failed to save.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-white dark:bg-slate-900">
    <!-- Header -->
    <div class="sticky top-0 z-10 bg-white/80 dark:bg-slate-900/80 backdrop-blur border-b border-slate-200 dark:border-slate-700">
      <div class="max-w-4xl mx-auto px-6 py-3 flex items-center gap-3">
        <a :href="`/watch/${filename}`" class="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-white transition-colors">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
        </a>
        <h1 class="text-lg font-semibold text-slate-800 dark:text-white truncate">{{ filename }}</h1>
        <span class="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">Summary</span>
        <button
          v-if="!loading && !error && !isEditing"
          @click="startEdit"
          class="ml-auto text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-800 transition-colors"
        >
          Edit
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="max-w-4xl mx-auto px-6 py-8">
      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
        <span class="ml-3 text-slate-500">Loading summary...</span>
      </div>
      <div v-else-if="error" class="text-center py-20">
        <p class="text-slate-400">{{ error }}</p>
      </div>
      <div v-else-if="isEditing" class="space-y-4">
        <textarea
          v-model="editContent"
          class="w-full min-h-[500px] px-4 py-3 font-mono text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
        ></textarea>
        <div class="flex gap-3">
          <button
            @click="saveEdit"
            :disabled="saving"
            class="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {{ saving ? 'Saving...' : 'Save' }}
          </button>
          <button
            @click="cancelEdit"
            class="px-4 py-2 text-sm rounded border border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
      <div
        v-else
        ref="containerRef"
        class="prose prose-slate max-w-none dark:prose-invert prose-headings:text-slate-900 dark:prose-headings:text-slate-100 prose-h1:text-2xl prose-h1:font-bold prose-h2:border-b prose-h2:border-slate-200 prose-h2:pb-2 prose-h2:text-xl prose-h2:font-bold dark:prose-h2:border-slate-700 prose-h3:text-lg prose-h3:font-semibold prose-p:leading-7 prose-a:text-blue-600 prose-a:underline-offset-4 hover:prose-a:underline dark:prose-a:text-blue-400 prose-ul:list-disc prose-ol:list-decimal prose-li:my-1 prose-blockquote:border-l-4 prose-blockquote:border-blue-400 prose-blockquote:bg-blue-50 prose-blockquote:px-4 prose-blockquote:py-2 prose-blockquote:font-normal prose-blockquote:italic prose-blockquote:text-slate-700 dark:prose-blockquote:bg-blue-950/30 dark:prose-blockquote:text-slate-200 prose-table:border-collapse prose-table:overflow-hidden prose-th:border prose-th:border-slate-300 prose-th:bg-slate-100 prose-th:px-3 prose-th:py-2 dark:prose-th:border-slate-700 dark:prose-th:bg-slate-800 prose-td:border prose-td:border-slate-200 prose-td:px-3 prose-td:py-2 dark:prose-td:border-slate-700 prose-tr:even:bg-slate-50 dark:prose-tr:even:bg-slate-800/50 prose-code:rounded prose-code:bg-slate-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-slate-800 dark:prose-code:bg-slate-800 dark:prose-code:text-slate-100 prose-pre:bg-slate-900 prose-pre:text-slate-100 dark:prose-pre:bg-slate-950 prose-img:mx-auto prose-img:w-auto prose-img:max-w-full sm:prose-img:max-w-[600px] prose-img:rounded-lg prose-img:shadow-lg prose-hr:border-slate-200 dark:prose-hr:border-slate-700"
        v-html="renderedHtml"
      ></div>
    </div>
  </div>
</template>
