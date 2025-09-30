<script setup lang="ts">
import { computed, defineProps, ref, defineEmits, watch, nextTick } from 'vue'
// 🔑 Import every ElementPlus icon you use:
import { Search, ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

interface SearchResult {
  id: number
  url: string
  title: string
  subtitle_matched: string[]
  notes_matched: string[]
  total_matched_nums: number
}

interface SearchResponse {
  results: SearchResult[]
  total_matches: number
  truncated: boolean
}

const props = defineProps<{
  /** the parent will pass `v-model:visible` into this */
  visible: boolean
}>()

/** 2. declare the update event */
const emit = defineEmits<{
  /** called when we want to tell the parent to change `visible` */
  (e: 'update:visible', value: boolean): void
}>()

// i18n functionality
const { t } = useI18n()

/** 3. a computed getter/setter that *maps* to the prop + emit */
const showSearch = computed<boolean>({
  get() {
    return props.visible
  },
  set(v: boolean) {
    emit('update:visible', v)
  },
})

// Search functionality
const searchQuery = ref('')
const searchResults = ref<SearchResult[]>([])
const isLoading = ref(false)
const totalMatches = ref(0)
const isTruncated = ref(false)
const modalInput = ref<HTMLInputElement | null>(null)

// Collapsible results state
const expandedVideos = ref<Set<number>>(new Set())

const handleOutsideClick = (event: MouseEvent) => {
  if ((event.target as HTMLElement).classList.contains('search-overlay')) {
    showSearch.value = false // this now emits update:visible
  }
}

// Focus input when modal opens
watch(
  () => props.visible,
  (newVal) => {
    if (newVal) {
      nextTick(() => {
        modalInput.value?.focus()
      })
    } else {
      // Clear search when modal closes
      searchQuery.value = ''
      searchResults.value = []
      expandedVideos.value.clear()
    }
  },
)

// Debounced search
let searchTimeout: number | null = null
import { BACKEND } from '@/composables/ConfigAPI'
import { getCSRFToken } from '@/composables/GetCSRFToken'
const performSearch = async () => {
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    totalMatches.value = 0
    isTruncated.value = false
    return
  }

  isLoading.value = true

  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/search/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({
        query: searchQuery.value,
      }),
    })

    if (!response.ok) {
      throw new Error('Search failed')
    }

    const data: SearchResponse = await response.json()
    searchResults.value = data.results
    totalMatches.value = data.total_matches
    isTruncated.value = data.truncated

    // Auto-expand results if there are few videos
    if (data.results.length <= 5) {
      expandedVideos.value = new Set(data.results.map((r) => r.id))
    } else {
      expandedVideos.value.clear()
    }
  } catch (error) {
    console.error('Search error:', error)
    searchResults.value = []
    totalMatches.value = 0
    isTruncated.value = false
  } finally {
    isLoading.value = false
  }
}

const onSearchInput = () => {
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }

  searchTimeout = setTimeout(() => {
    performSearch()
  }, 300) // 300ms debounce
}

const toggleVideoExpansion = (videoId: number) => {
  if (expandedVideos.value.has(videoId)) {
    expandedVideos.value.delete(videoId)
  } else {
    expandedVideos.value.add(videoId)
  }
}

const isVideoExpanded = (videoId: number) => {
  return expandedVideos.value.has(videoId)
}

// Handle keyboard navigation
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    showSearch.value = false
  } else if (event.key === 'Enter') {
    performSearch()
  }
}

// Add highlight function
const highlightSearchTerm = (text: string, searchTerm: string): string => {
  if (!searchTerm.trim()) return text

  const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
  return text.replace(regex, '<mark class="bg-yellow-200 px-1 rounded">$1</mark>')
}
</script>
<template>
  <!-- search -->
  <div
    v-if="showSearch"
    class="search-overlay fixed inset-0 bg-white/80 flex items-center justify-center z-50"
    @click="handleOutsideClick"
  >
    <div
      class="w-full max-w-4xl bg-white rounded-xl shadow-2xl overflow-hidden max-h-[80vh] flex flex-col"
      @click.stop
    >
      <!-- Search Input -->
      <div class="relative border-b border-gray-100">
        <input
          ref="modalInput"
          v-model="searchQuery"
          type="text"
          :placeholder="t('searchPlaceholder')"
          class="w-full py-5 px-6 text-lg border-0 focus:outline-none focus:ring-0"
          @input="onSearchInput"
          @keydown="handleKeydown"
        />
        <div v-if="isLoading" class="absolute right-4 top-1/2 transform -translate-y-1/2">
          <el-icon class="animate-spin text-gray-400"><Search /></el-icon>
        </div>
      </div>

      <!-- Search Results -->
      <div class="flex-1 overflow-y-auto">
        <!-- Truncation Warning Banner -->
        <div v-if="isTruncated" class="bg-red-600 text-white px-4 py-3 text-sm">
          <strong>{{ t('searchResultsTruncated') }}</strong>
        </div>

        <!-- Results Display -->
        <div v-if="searchResults.length > 0" class="p-4">
          <!-- Results Summary -->
          <div class="mb-4 text-sm text-gray-600">
            {{ t('foundResults', { count: searchResults.length, total: totalMatches }) }}
          </div>

          <!-- Video Results -->
          <div class="space-y-3">
            <div
              v-for="result in searchResults"
              :key="result.id"
              class="border border-gray-200 rounded-lg overflow-hidden hover:shadow-md transition-shadow"
            >
              <!-- Video Header (Collapsible) -->
              <div
                class="px-4 py-3 bg-gray-50 cursor-pointer flex items-center justify-between hover:bg-gray-100"
                @click="toggleVideoExpansion(result.id)"
              >
                <div class="flex items-center space-x-3">
                  <el-icon class="text-gray-500">
                    <ArrowDown v-if="isVideoExpanded(result.id)" />
                    <ArrowRight v-else />
                  </el-icon>
                  <a :href="`/watch/${encodeURIComponent(result.url)}`">
                    <h3 class="font-medium text-gray-900">{{ result.title }}</h3>
                  </a>
                  <span class="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded-full">
                    {{ result.total_matched_nums }}
                  </span>
                </div>
              </div>

              <!-- Expanded Content -->
              <div v-if="isVideoExpanded(result.id)" class="p-4 space-y-4">
                <!-- Subtitle Matches -->
                <div v-if="result.subtitle_matched.length > 0">
                  <h4 class="text-sm font-medium text-gray-700 mb-2 flex items-center">
                    <span class="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                    {{ t('subtitleMatches') }} ({{ result.subtitle_matched.length }})
                  </h4>
                  <div class="space-y-1">
                    <div
                      v-for="(line, index) in result.subtitle_matched"
                      :key="index"
                      class="text-sm text-gray-600 bg-green-50 px-3 py-2 rounded border-l-2 border-green-200"
                      v-html="highlightSearchTerm(line, searchQuery)"
                    ></div>
                  </div>
                </div>

                <!-- Notes Matches -->
                <div v-if="result.notes_matched.length > 0">
                  <h4 class="text-sm font-medium text-gray-700 mb-2 flex items-center">
                    <span class="w-2 h-2 bg-blue-500 rounded-full mr-2"></span>
                    {{ t('notesMatches') }} ({{ result.notes_matched.length }})
                  </h4>
                  <div class="space-y-1">
                    <div
                      v-for="(line, index) in result.notes_matched"
                      :key="index"
                      class="text-sm text-gray-600 bg-blue-50 px-3 py-2 rounded border-l-2 border-blue-200"
                      v-html="highlightSearchTerm(line, searchQuery)"
                    ></div>
                  </div>
                </div>

                <!-- No content matches (title only) -->
                <div
                  v-if="result.subtitle_matched.length === 0 && result.notes_matched.length === 0"
                >
                  <div class="text-sm text-gray-500 italic">{{ t('titleOnlyMatch') }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- No Results -->
        <div v-else-if="searchQuery.trim() && !isLoading" class="p-8 text-center text-gray-500">
          <el-icon class="text-3xl mb-3 text-gray-300"><Search /></el-icon>
          <p>{{ t('noResultsFound') }}</p>
          <p class="text-sm mt-1">{{ t('tryDifferentKeywords') }}</p>
        </div>

        <!-- Initial State -->
        <div v-else-if="!searchQuery.trim()" class="p-8 text-center text-gray-500">
          <el-icon class="text-3xl mb-3 text-gray-300"><Search /></el-icon>
          <p>{{ t('searchPrompt') }}</p>
          <p class="text-sm mt-1">{{ t('searchSupportNote') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
