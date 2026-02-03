<!-- 视频信息组件 -->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { markdownToHtml } from '@/composables/ConvertMarkdown'
import { getCSRFToken } from '@/composables/GetCSRFToken'
import NotesPanel from './NotesPanel.vue'
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
  <div class="bg-slate-800/30 rounded-2xl backdrop-blur-lg border border-slate-600/30">
    <!-- Tab Header -->
    <div class="border-b border-slate-600/30 p-2">
      <nav class="flex space-x-2 px-2">
        <button
          @click="activeTab = 'notes'"
          :class="[
            'flex-1 px-6 py-3 text-sm font-medium rounded-xl transition-all duration-300',
            activeTab === 'notes'
              ? 'text-white bg-blue-600/80 shadow-lg border border-blue-500/30'
              : 'text-slate-300 hover:text-white hover:bg-slate-700/50',
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
              : 'text-slate-300 hover:text-white hover:bg-slate-700/50',
          ]"
        >
          {{ t('videoQA') }}
        </button>
      </nav>
    </div>

    <!-- Tab Content -->
    <div class="p-0">
      <!-- Notes Tab -->
      <div v-show="activeTab === 'notes'">
        <NotesPanel :videoId="props.id" />
      </div>

      <!-- Video Q&A Tab -->
      <div v-show="activeTab === 'videoQA'" class="p-12 flex flex-col items-center justify-center text-center space-y-4">
        <div class="w-20 h-20 bg-blue-500/10 rounded-full flex items-center justify-center mb-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-10 w-10 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        </div>
        <h3 class="text-xl font-semibold text-white">Video Q&A</h3>
        <p class="text-slate-400 max-w-xs">
          Coming soon, involves VLA model.
        </p>
        <div class="px-3 py-1 bg-slate-700/50 rounded-full text-xs font-medium text-slate-300 border border-slate-600/50">
          Planned Feature
        </div>
      </div>
    </div>
  </div>
</template>
