<!-- 视频信息组件 -->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { markdownToHtml } from '@/composables/ConvertMarkdown'
import { getCSRFToken } from '@/composables/GetCSRFToken'
import NotesPanel from './NotesPanel.vue'
import VideoQA from './VideoQA.vue'
import { useI18n } from 'vue-i18n'
import { BACKEND } from '@/composables/ConfigAPI'

// i18n functionality
const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    filename: string
    title: string
    description: string
    id: number
  }>(),
  {
    description: '',
  },
)

// Tab management
const activeTab = ref('notes')

const emit = defineEmits<{
  (e: 'update:description', value: string): void
}>()

// tool function for communication with backend
async function updateDescription(videoId: number, description: string) {
  try {
    const csrf = await getCSRFToken()
    const res = await fetch(`${BACKEND}/video/rename_description/${props.id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      body: JSON.stringify({ video_id: videoId, description: description }),
    })

    if (!res.ok) {
      throw new Error((await res.text()) || 'Request failed')
    }
    return await res.json()
  } catch (err) {
    console.error(err)
  }
}

// Status interaction for frontend
const isEditing = ref(false)
const draftDesc = ref(props.description)
function startEdit() {
  draftDesc.value = props.description
  isEditing.value = true
}

async function save() {
  const newDesc = draftDesc.value.trim() // trimming  extra space

  isEditing.value = false
  if (!newDesc || newDesc === props.description) return

  try {
    await updateDescription(props.id, newDesc)
    emit('update:description', newDesc) // ← now recognised
  } catch (err) {
    console.error(err)
    draftDesc.value = props.description // rollback on failure
  }
}

const renderedDescription = computed(() =>
  markdownToHtml(isEditing.value ? draftDesc.value : props.description),
)
</script>

<template>
  <div class="bg-white dark:bg-slate-800/30 rounded-2xl backdrop-blur-lg border border-slate-200 dark:border-slate-600/30 flex flex-col overflow-hidden">
    <!-- Tab Header -->
    <div class="flex-shrink-0 border-b border-slate-200 dark:border-slate-600/30 p-2">
      <nav class="flex space-x-2 px-2">
        <button
          @click="activeTab = 'notes'"
          :class="[
            'flex-1 px-6 py-3 text-sm font-medium rounded-xl transition-all duration-300',
            activeTab === 'notes'
              ? 'text-white bg-blue-600/80 shadow-lg border border-blue-500/30'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-700/50',
          ]"
        >
          {{ t('notes') }}
        </button>
        <button
          @click="activeTab = 'videoQA'"
          :class="[
            'flex-1 px-6 py-3 text-sm font-medium rounded-xl transition-all duration-300',
            activeTab === 'videoQA'
              ? 'text-white bg-blue-600/80 shadow-lg border border-blue-500/30'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-700/50',
          ]"
        >
          {{ t('videoQA') }}
        </button>
      </nav>
    </div>

    <!-- Tab Content -->
    <div class="flex-1 min-h-0 overflow-hidden">
      <!-- Notes Tab -->
      <div v-show="activeTab === 'notes'" class="h-full overflow-y-auto">
        <NotesPanel :videoId="props.id" />
      </div>

      <!-- Video Q&A Tab -->
      <div v-show="activeTab === 'videoQA'" class="h-full">
        <VideoQA :videoId="props.id" :filename="props.filename" />
      </div>
    </div>
  </div>
</template>
