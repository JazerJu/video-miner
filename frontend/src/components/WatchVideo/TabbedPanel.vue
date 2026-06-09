<script setup lang="ts">
import { ref } from 'vue'
import SubtitlePanel from './SubtitlePanel.vue'
import VideoChapters from './VideoChapters.vue'
import { useI18n } from 'vue-i18n'

// i18n functionality
const { t } = useI18n()

const props = defineProps<{
  currentTime: number
  id: number
  rawLang?: string
  videoName?: string
  showChapterMarkers?: boolean
}>()

const emit = defineEmits<{
  (e: 'seek', time: number): void
  (e: 'update-bloburls', blobUrls: Array<string | undefined>): void
  (e: 'toggle-chapter-markers', show: boolean): void
}>()

const activeTab = ref<'subtitles' | 'chapters'>('subtitles')
// 保持字幕翻译开关状态，避免切换标签页时丢失
const showTranslation = ref(false)
</script>

<template>
  <div class="bg-white dark:bg-slate-800/30 rounded-2xl backdrop-blur-lg border border-slate-200 dark:border-slate-600/30">
    <!-- Tab Navigation -->
    <div class="flex border-b border-slate-200 dark:border-slate-600/30 p-2">
      <button
        @click="activeTab = 'subtitles'"
        class="flex-1 px-6 py-3 text-sm font-medium rounded-xl transition-all duration-300 mx-1"
        :class="
          activeTab === 'subtitles'
            ? 'text-white bg-blue-600/80 shadow-lg border border-blue-500/30'
            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-700/50'
        "
      >
        {{ t('subtitles') }}
      </button>
      <button
        @click="activeTab = 'chapters'"
        class="flex-1 px-6 py-3 text-sm font-medium rounded-xl transition-all duration-300 mx-1"
        :class="
          activeTab === 'chapters'
            ? 'text-white bg-blue-600/80 shadow-lg border border-blue-500/30'
            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-700/50'
        "
      >
        {{ t('videoChapters') }}
      </button>
    </div>

    <!-- Tab Content -->
    <div class="tab-content">
      <!-- Subtitles Tab -->
      <div v-show="activeTab === 'subtitles'" class="p-0">
        <SubtitlePanel
          :current-time="currentTime"
          :id="id"
          :rawLang="rawLang"
          :videoName="videoName"
          v-model:show-translation="showTranslation"
          @seek="emit('seek', $event)"
          @update-bloburls="emit('update-bloburls', $event)"
        />
      </div>

      <!-- Video Chapters Tab -->
      <div v-show="activeTab === 'chapters'" class="p-0">
        <VideoChapters
          :current-time="currentTime"
          :id="id"
          :showChapterMarkers="showChapterMarkers"
          @seek="emit('seek', $event)"
          @toggle-chapter-markers="emit('toggle-chapter-markers', $event)"
        />
      </div>

    </div>
  </div>
</template>

<style scoped>
.tab-content {
  min-height: 400px;
}
</style>
