<!-- 字幕编辑器核心 -->
<template>
  <!-- All elements for subtitle Editor,In card vision -->
  <div class="w-full h-full flex flex-col">
    <!-- Subtitle List -->
    <div class="h-full">
      <div class="h-full">
        <div class="p-6 h-full flex flex-col">
          <div class="flex items-center justify-between mb-6 flex-shrink-0">
            <!-- Time Filter Button -->
            <button
              @click="openTimeFilter"
              class="flex items-center space-x-2 px-3 py-2 bg-white/80 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 text-slate-700 dark:text-slate-200 rounded-lg transition-colors border border-slate-200 dark:border-white/10"
              :class="{ 'border-blue-500/50 bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-200': filterStartTime !== null || filterEndTime !== null }"
            >
              <el-icon><Clock /></el-icon>
              <span class="font-semibold">{{ (filterStartTime !== null || filterEndTime !== null) ? t('filtered') : t('subtitleList') }}</span>
            </button>
            <div class="flex space-x-3">
              <!-- 批量删除 -->
              <template v-if="selectedIndices.size > 0">
                <el-tooltip :content="t('deleteSelected')" placement="bottom">
                  <button
                    @click="batchDelete"
                    class="px-4 py-2 bg-red-600/80 hover:bg-red-600 text-white text-sm rounded-lg transition-colors backdrop-blur-sm border border-red-500/30"
                  >
                    <el-icon><Delete /></el-icon>
                  </button>
                </el-tooltip>
                <!-- 批量合并（至少选2条才启用） -->
                <el-tooltip :content="t('mergeSelected')" placement="bottom">
                  <button
                    @click="batchMerge"
                    :disabled="selectedIndices.size < 2"
                  class="px-4 py-2 bg-purple-600/80 hover:bg-purple-600 disabled:opacity-40 text-white text-sm rounded-lg transition-colors backdrop-blur-sm border border-purple-500/30"
                  >
                    <el-icon><Finished /></el-icon>
                  </button>
                </el-tooltip>
              </template>

              <!-- 添加字幕的按钮 -->
              <el-tooltip :content="t('addSubtitle')" placement="bottom">
                <button
                  @click="addSubtitle"
                  class="px-4 py-2 bg-blue-600/80 hover:bg-blue-600 text-white text-sm rounded-lg transition-colors backdrop-blur-sm border border-blue-500/30"
                >
                  <el-icon><Plus /></el-icon>
                </button>
              </el-tooltip>

              <!-- 导出按钮 -->
              <el-dropdown @command="handleExport" trigger="click">
                <button
                  class="px-4 py-2 bg-white/80 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 text-slate-700 dark:text-slate-300 text-sm rounded-lg transition-colors border border-slate-200 dark:border-white/10"
                >
                  <el-icon><Upload /></el-icon> {{ t('export') }}
                </button>
                <template #dropdown>
                  <el-dropdown-menu
                    class="rounded-lg shadow-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-800"
                  >
                    <div
                      class="text-xs text-slate-600 dark:text-white px-4 py-2 bg-slate-50 dark:bg-white/5 uppercase tracking-wide font-semibold"
                    >
                      {{ t('textKind') }}
                    </div>
                    <el-dropdown-item
                      command="vtt"
                      class="hover:bg-slate-100 dark:hover:bg-white/10 hover:text-blue-600 dark:hover:text-blue-400 transition-colors text-slate-700 dark:text-slate-300"
                    >
                      VTT
                    </el-dropdown-item>
                    <el-dropdown-item
                      command="txt"
                      class="hover:bg-slate-100 dark:hover:bg-white/10 hover:text-blue-600 dark:hover:text-blue-400 transition-colors text-slate-700 dark:text-slate-300"
                    >
                      TXT
                    </el-dropdown-item>
                    <el-dropdown-item
                      command="srt"
                      class="hover:bg-slate-100 dark:hover:bg-white/10 hover:text-blue-600 dark:hover:text-blue-400 transition-colors text-slate-700 dark:text-slate-300"
                    >
                      SRT
                    </el-dropdown-item>
                    <el-dropdown-item
                      command="ass"
                      class="hover:bg-slate-100 dark:hover:bg-white/10 hover:text-blue-600 dark:hover:text-blue-400 transition-colors text-slate-700 dark:text-slate-300"
                    >
                      ASS
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <!-- 字幕数量标签 -->
            <span
              class="bg-blue-600/20 text-blue-400 px-3 py-1 rounded-full text-xs font-medium border border-blue-500/30"
            >
              {{ filteredSubtitles.length }} {{ t('items') }}
            </span>
          </div>

          <div
            ref="subtitleListContainer"
            @scroll="handleManualScroll"
            class="space-y-4 flex-1 overflow-y-auto custom-scrollbar min-h-0 pr-2 relative"
          >
            <div
              v-for="(s, i) in filteredSubtitles"
              :key="s.originalIndex"
              :ref="
                (el) => {
                  if (el) subtitleRefs[s.originalIndex] = el as HTMLElement
                }
              "
              :class="[
                'p-4 rounded-xl border-2 transition-all duration-200 cursor-pointer backdrop-blur-sm',
                activeSubtitleIndex === s.originalIndex
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30 shadow-lg'
                  : currentSubtitleIndex === s.originalIndex
                    ? 'border-green-500 bg-green-50 dark:bg-green-900/30 shadow-md'
                    : 'border-slate-200 bg-slate-50/80 hover:border-slate-300 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:border-white/20 dark:hover:bg-white/10',
              ]"
              @click="setActiveSubtitle(s.originalIndex)"
            >
              <div class="flex items-start justify-between mb-3">
                <div class="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    :checked="selectedIndices.has(s.originalIndex)"
                    @click.stop="toggleSelect(s.originalIndex)"
                    class="w-4 h-4 rounded accent-blue-500 cursor-pointer"
                  />
                  <span class="text-sm font-medium text-slate-500 dark:text-slate-400">#{{ s.originalIndex }}</span>
                  <span
                    :class="[
                      'text-xs px-2 py-1 rounded-full border',
                      getCharacterSpeedColor(calculateCPS(s)),
                    ]"
                  >
                    {{ calculateCPS(s) }} {{ getSpeedUnit(s.text) }}
                  </span>
                </div>
                <div class="flex space-x-1">
                  <button
                    @click.stop="startEdit(s.originalIndex)"
                    class="h-6 w-6 p-0 hover:bg-blue-50 dark:hover:bg-blue-600/20 rounded flex items-center justify-center transition-colors text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    <Edit3Icon class="w-3 h-3" />
                  </button>
                </div>
              </div>

              <div class="space-y-2">
                <div class="text-xs font-mono text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-white/5 px-2 py-1 rounded-md">
                  {{ s.start }} → {{ s.end }}
                </div>
                <!-- if Editing index !=i display plain text as below,if Editing index ==i,change into input -->
                <!-- ▸ EDITING STATE  -->
                <template v-if="editSubtitleIndex === s.originalIndex">
                  <!-- 时间区域 -->
                  <div class="flex gap-3 mb-3">
                    <div class="flex-1">
                      <label class="text-xs text-slate-500 dark:text-slate-400 block mb-1">{{ t('startTimeSeconds') }}</label>
                      <input
                        type="number"
                        step="0.01"
                        v-model.number="rawSubtitle[s.originalIndex].start"
                        @change="syncForeignTiming(s.originalIndex)"
                        class="w-full px-3 py-2 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white text-sm"
                      />
                    </div>
                    <div class="flex-1">
                      <label class="text-xs text-slate-500 dark:text-slate-400 block mb-1">{{ t('endTimeSeconds') }}</label>
                      <input
                        type="number"
                        step="0.01"
                        v-model.number="rawSubtitle[s.originalIndex].end"
                        @change="syncForeignTiming(s.originalIndex)"
                        class="w-full px-3 py-2 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white text-sm"
                      />
                    </div>
                  </div>

                  <!-- 原文 -->
                  <div v-if="showRawEditor" class="space-y-2">
                    <label class="text-xs text-slate-500 dark:text-slate-400 block">{{ t('original') }}:</label>
                    <textarea
                      v-model="rawSubtitle[s.originalIndex].text"
                      class="w-full p-3 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white placeholder-slate-400 resize-none"
                      :placeholder="t('enterSubtitleOriginal')"
                      rows="2"
                    />
                  </div>

                  <!-- 译文 -->
                  <div v-if="showTranslatedEditor" class="space-y-2">
                    <label class="text-xs text-slate-500 dark:text-slate-400 block"
                      >{{ t('translatedSubtitle') }}:</label
                    >
                    <textarea
                      v-model="foreignSubtitle[s.originalIndex].text"
                      class="w-full p-3 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white placeholder-slate-400 resize-none"
                      :placeholder="t('enterSubtitleTranslation')"
                      rows="2"
                    />
                  </div>

                  <div class="flex gap-2 mt-3">
                    <button
                      @click.stop="saveSubtitle(s.originalIndex)"
                      class="px-3 py-1 bg-blue-600/80 hover:bg-blue-600 text-white text-sm rounded-lg transition-colors"
                    >
                      {{ t('save') }}
                    </button>
                    <button
                      @click.stop="cancelEdit"
                      class="px-3 py-1 bg-slate-100 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10 text-slate-700 dark:text-slate-300 text-sm rounded-lg transition-colors"
                    >
                      {{ t('cancel') }}
                    </button>
                  </div>
                </template>

                <!-- ▸ READ-ONLY STATE  -->
                <template v-else>
                  <div class="text-sm text-slate-900 dark:text-white leading-relaxed" v-show="displayMode === 'both' || displayMode === 'raw'">
                    <span class="text-xs text-slate-500 dark:text-slate-400 block mb-1">{{ t('original') }}:</span>
                    {{ s.text }}
                  </div>

                  <div class="border-t border-slate-200 dark:border-white/10 my-2" v-show="displayMode === 'both'" />

                  <div class="text-sm text-slate-700 dark:text-slate-200 leading-relaxed" v-show="displayMode === 'both' || displayMode === 'translated'">
                    <span class="text-xs text-slate-500 dark:text-slate-400 block mb-1"
                      >{{ t('translatedSubtitle') }}:</span
                    >
                    {{ s.translation }}
                  </div>
                </template>
              </div>
            </div>

            <!-- Floating Ball -->
            <div
              v-show="showFloatingBall"
              @click="scrollToCurrentSubtitle"
              class="fixed bottom-6 right-6 w-10 h-10 bg-green-600/70 hover:bg-green-500/80 text-white rounded-full shadow-md cursor-pointer transition-all duration-200 flex items-center justify-center z-50"
            >
              <ArrowBigDown class="w-5 h-5" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Language Selection Dialog -->
    <div
      v-if="showLanguageDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showLanguageDialog = false"
    >
      <div class="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-96 border border-slate-200 dark:border-white/10">
        <div class="p-6">
          <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">{{ t('selectExportLanguage') }}</h3>
          <div class="space-y-3">
            <button
              @click="exportWithLanguage('raw')"
              class="w-full p-3 text-left bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 text-slate-900 dark:text-white rounded-lg transition-colors border border-slate-200 dark:border-white/10"
            >
              <div class="font-medium">{{ t('originalSubtitle') }}</div>
              <div class="text-sm text-slate-600 dark:text-slate-300">{{ t('rawSubtitleDesc') }}</div>
            </button>
            <button
              @click="exportWithLanguage('translated')"
              class="w-full p-3 text-left bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 text-slate-900 dark:text-white rounded-lg transition-colors border border-slate-200 dark:border-white/10"
            >
              <div class="font-medium">{{ t('translatedSubtitleFull') }}</div>
              <div class="text-sm text-slate-600 dark:text-slate-300">{{ t('translatedSubtitleDesc') }}</div>
            </button>
            <button
              @click="exportWithLanguage('both')"
              class="w-full p-3 text-left bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 text-slate-900 dark:text-white rounded-lg transition-colors border border-slate-200 dark:border-white/10"
            >
              <div class="font-medium">{{ t('bilingualSubtitle') }}</div>
              <div class="text-sm text-slate-600 dark:text-slate-300">{{ t('bilingualSubtitleDesc') }}</div>
            </button>
          </div>
          <div class="mt-4 text-right">
            <button
              @click="showLanguageDialog = false"
              class="px-4 py-2 text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white transition-colors"
            >
              {{ t('cancel') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Time Filter Dialog -->
    <div
      v-if="showTimeFilterDialog"
      class="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
      @click.self="showTimeFilterDialog = false"
    >
      <div class="bg-white/95 dark:bg-slate-800/95 rounded-2xl p-8 w-full max-w-md border border-slate-200 dark:border-white/10 shadow-2xl shadow-slate-300/70 dark:shadow-black/30 backdrop-blur-lg">
        <h3 class="text-xl font-semibold text-slate-900 dark:text-white mb-6">{{ t('subtitleTimeFilter') }}</h3>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-600 dark:text-slate-400 mb-2">{{ t('startTimeSeconds') }}</label>
            <input
              v-model.number="editFilterStart"
              type="number"
              min="0"
              :placeholder="t('exampleSeconds', { seconds: 60 })"
              class="w-full px-4 py-2 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white placeholder-slate-400"
            />
          </div>
          <div>
            <label class="block text-sm text-slate-600 dark:text-slate-400 mb-2">{{ t('endTimeSeconds') }}</label>
            <input
              v-model.number="editFilterEnd"
              type="number"
              min="0"
              :placeholder="t('exampleSeconds', { seconds: 120 })"
              class="w-full px-4 py-2 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-slate-900 dark:text-white placeholder-slate-400"
            />
          </div>
          <div>
            <label class="block text-sm text-slate-600 dark:text-slate-400 mb-2">{{ t('subtitleDisplay') }}</label>
            <div class="flex gap-2">
              <button
                v-for="mode in displayModeOptions"
                :key="mode.value"
                @click="editDisplayMode = mode.value as any"
                :class="[
                  'flex-1 py-2 rounded-lg text-sm transition-colors border',
                  editDisplayMode === mode.value
                    ? 'bg-blue-600/80 border-blue-500/30 text-white'
                    : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100 dark:bg-white/5 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10'
                ]"
              >
                {{ mode.label }}
              </button>
            </div>
          </div>
        </div>

        <div class="flex justify-between items-center mt-8">
          <button
            @click="clearTimeFilter"
            class="text-sm text-red-400 hover:text-red-300 transition-colors"
          >
            {{ t('clearFilter') }}
          </button>
          <div class="space-x-3">
            <button
              @click="showTimeFilterDialog = false"
              class="px-4 py-2 text-slate-700 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white bg-slate-100 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10 rounded-lg transition-all border border-slate-200 dark:border-white/10"
            >
              {{ t('cancel') }}
            </button>
            <button
              @click="applyTimeFilter"
              class="px-4 py-2 bg-blue-600/80 hover:bg-blue-600 text-white rounded-lg transition-all border border-blue-500/30 shadow-lg"
            >
              {{ t('apply') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Actions -->
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { Plus, ArrowDown, Delete, Finished } from '@element-plus/icons-vue'
import { useSubtitles } from '@/composables/useSubtitles'
import { blobUrls, generateVTT } from '@/composables/Buildvtt'
import type { Subtitle } from '@/types/subtitle'
import {
  Edit3 as Edit3Icon,
  ArrowBigDown,
  Clock,
} from 'lucide-vue-next'
import { ElMessage } from '@/composables/useNotification'
import { Upload, Download } from '@element-plus/icons-vue'
import { loadConfig } from '@/composables/ConfigAPI'
import { useI18n } from 'vue-i18n'
import { getCookie } from '@/composables/GetCSRFToken'
import { useNotification } from '@/composables/useNotification'

const { subtitles, linkSubtitles, fetchSubtitle } = useSubtitles()
import { BACKEND } from '@/composables/ConfigAPI'

const props = defineProps<{
  currentTime: number
  id: number
  rawLang?: string
  videoName?: string
  duration: number
  /** vue-i18n composer instance for translations */
  i18n?: ReturnType<typeof useI18n>
}>()

// i18n composer (use provided one or fall back to local)
const i18nComposer = props.i18n ?? useI18n()
const t = i18nComposer.t as any
const locale = i18nComposer.locale

const { success: successNotify, error: errorNotify, info: infoNotify } = useNotification()

const rawSubtitle = ref<Subtitle[]>(subtitles.value)
const foreignSubtitle = ref<Subtitle[]>(subtitles.value)

const bilingualSubs = computed(() =>
  rawSubtitle.value.map((orig, i) => ({
    start: orig.start,
    end: orig.end,
    text: orig.text,
    translation: foreignSubtitle.value[i]?.text ?? '',
    originalIndex: i,
  })),
)

// Filter Logic
const filterStartTime = ref<number | null>(null)
const filterEndTime = ref<number | null>(null)
const showTimeFilterDialog = ref(false)
const editFilterStart = ref<number | null>(null)
const editFilterEnd = ref<number | null>(null)

// 显示模式：'both' | 'raw' | 'translated'
const displayMode = ref<'both' | 'raw' | 'translated'>('both')
const editDisplayMode = ref<'both' | 'raw' | 'translated'>('both')
const displayModeOptions = computed(() => [
  { value: 'both' as const, label: t('bilingual') },
  { value: 'raw' as const, label: t('original') },
  { value: 'translated' as const, label: t('translatedSubtitle') },
])
const showRawEditor = computed(() => displayMode.value !== 'translated')
const showTranslatedEditor = computed(() => displayMode.value !== 'raw')
const foreignTrackLoaded = ref(false)

function hasForeignContent(track: Subtitle[] = foreignSubtitle.value) {
  return track.some((sub) => sub?.text?.trim())
}

function shouldPersistForeignTrack() {
  return foreignTrackLoaded.value || hasForeignContent()
}

function ensureForeignSubtitle(index: number): Subtitle {
  if (!foreignSubtitle.value[index]) {
    const raw = rawSubtitle.value[index]
    foreignSubtitle.value[index] = {
      start: raw?.start ?? 0,
      end: raw?.end ?? raw?.start ?? 0,
      text: '',
    }
  }

  return foreignSubtitle.value[index]
}

function syncForeignTiming(index: number) {
  const raw = rawSubtitle.value[index]
  const foreign = foreignSubtitle.value[index]

  if (!raw || !foreign) return

  foreign.start = raw.start
  foreign.end = raw.end
}

function setBlobUrl(index: number, nextUrl: string | undefined) {
  const currentUrl = blobUrls.value[index]
  if (currentUrl && currentUrl !== nextUrl) {
    URL.revokeObjectURL(currentUrl)
  }
  blobUrls.value[index] = nextUrl
}

function updateBlobTracks() {
  setBlobUrl(
    0,
    rawSubtitle.value.length > 0 ? generateVTT('primary', [rawSubtitle.value]) : undefined,
  )

  const hasForeignTrack = foreignSubtitle.value.length > 0 && shouldPersistForeignTrack()

  setBlobUrl(
    1,
    hasForeignTrack ? generateVTT('translation', [foreignSubtitle.value]) : undefined,
  )
  setBlobUrl(
    2,
    rawSubtitle.value.length > 0 && hasForeignTrack
      ? generateVTT('both', [rawSubtitle.value, foreignSubtitle.value])
      : undefined,
  )
}

// Filtered subtitles based on time range
const filteredSubtitles = computed(() => {
  if (filterStartTime.value === null && filterEndTime.value === null) {
    return bilingualSubs.value
  }

  return bilingualSubs.value.filter((sub) => {
    if (filterStartTime.value !== null && sub.end < filterStartTime.value) return false
    if (filterEndTime.value !== null && sub.start > filterEndTime.value) return false
    return true
  })
})

const openTimeFilter = () => {
  editFilterStart.value = filterStartTime.value
  editFilterEnd.value = filterEndTime.value
  editDisplayMode.value = displayMode.value
  showTimeFilterDialog.value = true
}

const applyTimeFilter = () => {
  if (
    editFilterStart.value !== null &&
    editFilterEnd.value !== null &&
    editFilterStart.value > editFilterEnd.value
  ) {
    ElMessage.error(t('startTimeGreaterThanEnd'))
    return
  }
  filterStartTime.value = editFilterStart.value
  filterEndTime.value = editFilterEnd.value
  displayMode.value = editDisplayMode.value
  showTimeFilterDialog.value = false
}

const clearTimeFilter = () => {
  filterStartTime.value = null
  filterEndTime.value = null
  editFilterStart.value = null
  editFilterEnd.value = null
  showTimeFilterDialog.value = false
}

function handleExport(command: string) {
  if (['vtt', 'srt', 'txt', 'ass'].includes(command)) {
    pendingExportFormat.value = command
    showLanguageDialog.value = true
  }
}

// Language selection function
function exportWithLanguage(languageType: 'raw' | 'translated' | 'both') {
  showLanguageDialog.value = false

  const format = pendingExportFormat.value
  switch (format) {
    case 'vtt':
      exportVTT(languageType)
      break
    case 'srt':
      exportSRT(languageType)
      break
    case 'txt':
      exportTXT(languageType)
      break
    case 'ass':
      exportASS(languageType)
      break
  }
}

// Export functions
function exportVTT(languageType: 'raw' | 'translated' | 'both' = 'both') {
  const fmt = (t: number) => new Date(t * 1000).toISOString().substring(11, 23)

  let vtt = 'WEBVTT\n\n'
  bilingualSubs.value.forEach((sub) => {
    let textBlock = ''
    switch (languageType) {
      case 'raw':
        textBlock = sub.text
        break
      case 'translated':
        textBlock = sub.translation || sub.text
        break
      case 'both':
        textBlock = sub.translation ? `${sub.text}\n${sub.translation}` : sub.text
        break
    }
    vtt += `${fmt(sub.start)} --> ${fmt(sub.end)}\n${textBlock}\n\n`
  })

  const suffix =
    languageType === 'raw' ? '_raw' : languageType === 'translated' ? '_translated' : ''
  downloadFile(vtt, `${props.videoName || 'subtitles'}${suffix}.vtt`, 'text/vtt')
  successNotify(t('vttExportSuccess'))
}

function exportSRT(languageType: 'raw' | 'translated' | 'both' = 'both') {
  const fmt = (t: number) => {
    const date = new Date(t * 1000)
    return date.toISOString().substring(11, 23).replace('.', ',')
  }

  let srt = ''
  bilingualSubs.value.forEach((sub, i) => {
    let textBlock = ''
    switch (languageType) {
      case 'raw':
        textBlock = sub.text
        break
      case 'translated':
        textBlock = sub.translation || sub.text
        break
      case 'both':
        textBlock = sub.translation ? `${sub.text}\n${sub.translation}` : sub.text
        break
    }
    srt += `${i + 1}\n${fmt(sub.start)} --> ${fmt(sub.end)}\n${textBlock}\n\n`
  })

  const suffix =
    languageType === 'raw' ? '_raw' : languageType === 'translated' ? '_translated' : ''
  downloadFile(srt, `${props.videoName || 'subtitles'}${suffix}.srt`, 'text/srt')
  successNotify(t('srtExportSuccess'))
}

function exportTXT(languageType: 'raw' | 'translated' | 'both' = 'both') {
  let txt = ''
  bilingualSubs.value.forEach((sub) => {
    let textBlock = ''
    switch (languageType) {
      case 'raw':
        textBlock = sub.text
        break
      case 'translated':
        textBlock = sub.translation || sub.text
        break
      case 'both':
        textBlock = sub.translation ? `${sub.text}\n${sub.translation}` : sub.text
        break
    }
    txt += `${textBlock}\n\n`
  })

  const suffix =
    languageType === 'raw' ? '_raw' : languageType === 'translated' ? '_translated' : ''
  downloadFile(txt, `${props.videoName || 'subtitles'}${suffix}.txt`, 'text/plain')
  successNotify(t('txtExportSuccess'))
}

async function exportASS(languageType: 'raw' | 'translated' | 'both' = 'both') {
  // Load subtitle styling configuration
  let subtitleSettings: any = {}
  try {
    const config = await loadConfig()
    subtitleSettings = config
  } catch (error) {
    console.warn('Failed to load subtitle settings, using defaults:', error)
    // Default settings fallback
    subtitleSettings = {
      fontFamily: '宋体',
      fontSize: 18,
      fontColor: '#ea9749',
      fontWeight: '400',
      backgroundColor: '#000000',
      backgroundStyle: 'semi-transparent',
      borderRadius: 4,
      textShadow: false,
      bottomDistance: 80,
      foreignFontFamily: 'Arial',
      foreignFontSize: 16,
      foreignFontColor: '#ffffff',
      foreignFontWeight: '400',
      foreignBackgroundColor: '#000000',
      foreignBackgroundStyle: 'semi-transparent',
      foreignBorderRadius: 4,
      foreignTextShadow: false,
      foreignBottomDistance: 120,
    }
  }

  // Get video dimensions
  let width = 1920,
    height = 1080 // Default resolution
  try {
    const response = await fetch(`${BACKEND}/api/videos/${props.id}/get_dimensions`, {
      method: 'GET',
      credentials: 'include',
    })
    const result = await response.json()
    if (result.success) {
      width = result.width
      height = result.height
      console.log(`Using video dimensions: ${width}x${height}`)
    } else {
      console.warn('Failed to get video dimensions:', result.error)
    }
  } catch (error) {
    console.warn('Error getting video dimensions:', error)
  }

  const fmt = (t: number) => {
    const totalSeconds = Math.floor(t)
    const hours = Math.floor(totalSeconds / 3600)
    const minutes = Math.floor((totalSeconds % 3600) / 60)
    const seconds = totalSeconds % 60
    const centiseconds = Math.floor((t - totalSeconds) * 100)
    return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${centiseconds.toString().padStart(2, '0')}`
  }

  // Convert hex color to ASS color format (BGR)
  const hexToAssColor = (hex: string) => {
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    return `&H00${b.toString(16).padStart(2, '0').toUpperCase()}${g.toString(16).padStart(2, '0').toUpperCase()}${r.toString(16).padStart(2, '0').toUpperCase()}`
  }

  // Generate ASS header with styling (use actual video resolution info for proper scaling)
  let ass = `[Script Info]
Title: ${props.videoName || 'Exported Subtitles'}
ScriptType: v4.00+
PlayResX: ${width}
PlayResY: ${height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
`

  // Add styles based on language type
  if (languageType === 'raw' || languageType === 'both') {
    const rawColor = hexToAssColor(
      subtitleSettings.font_color || subtitleSettings.fontColor || '#ea9749',
    )
    const rawBgColor = hexToAssColor(
      subtitleSettings.background_color || subtitleSettings.backgroundColor || '#000000',
    )
    const rawFontSize = subtitleSettings.font_size || subtitleSettings.fontSize || 18
    const rawBold =
      parseInt(subtitleSettings.font_weight || subtitleSettings.fontWeight || '400') > 500 ? -1 : 0
    const rawShadow = subtitleSettings.text_shadow || subtitleSettings.textShadow ? 2 : 0
    const rawMarginV = subtitleSettings.bottom_distance || subtitleSettings.bottomDistance || 80

    // Add text stroke (outline) support
    const rawStroke =
      subtitleSettings.text_stroke || subtitleSettings.textStroke
        ? subtitleSettings.text_stroke_width || subtitleSettings.textStrokeWidth || 2
        : 0
    const rawStrokeColor =
      subtitleSettings.text_stroke || subtitleSettings.textStroke
        ? hexToAssColor(
            subtitleSettings.text_stroke_color || subtitleSettings.textStrokeColor || '#000000',
          )
        : '&H00000000'

    ass += `Style: Raw,${subtitleSettings.font_family || subtitleSettings.fontFamily || '宋体'},${rawFontSize},${rawColor},${rawColor},${rawStrokeColor},${rawBgColor},${rawBold},0,0,0,100,100,0,0,1,${rawStroke},${rawShadow},2,0,0,${rawMarginV},1\n`
  }

  if (languageType === 'translated' || languageType === 'both') {
    const transColor = hexToAssColor(
      subtitleSettings.foreign_font_color || subtitleSettings.foreignFontColor || '#ffffff',
    )
    const transBgColor = hexToAssColor(
      subtitleSettings.foreign_background_color ||
        subtitleSettings.foreignBackgroundColor ||
        '#000000',
    )
    const transFontSize =
      subtitleSettings.foreign_font_size || subtitleSettings.foreignFontSize || 16
    const transBold =
      parseInt(
        subtitleSettings.foreign_font_weight || subtitleSettings.foreignFontWeight || '400',
      ) > 500
        ? -1
        : 0
    const transShadow =
      subtitleSettings.foreign_text_shadow || subtitleSettings.foreignTextShadow ? 2 : 0
    const transMarginV =
      subtitleSettings.foreign_bottom_distance || subtitleSettings.foreignBottomDistance || 120

    // Add text stroke (outline) support
    const transStroke =
      subtitleSettings.foreign_text_stroke || subtitleSettings.foreignTextStroke
        ? subtitleSettings.foreign_text_stroke_width || subtitleSettings.foreignTextStrokeWidth || 2
        : 0
    const transStrokeColor =
      subtitleSettings.foreign_text_stroke || subtitleSettings.foreignTextStroke
        ? hexToAssColor(
            subtitleSettings.foreign_text_stroke_color ||
              subtitleSettings.foreignTextStrokeColor ||
              '#000000',
          )
        : '&H00000000'

    ass += `Style: Foreign,${subtitleSettings.foreign_font_family || subtitleSettings.foreignFontFamily || 'Arial'},${transFontSize},${transColor},${transColor},${transStrokeColor},${transBgColor},${transBold},0,0,0,100,100,0,0,1,${transStroke},${transShadow},2,0,0,${transMarginV},1\n`
  }

  ass += `
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
`

  // Add dialogue lines
  bilingualSubs.value.forEach((sub) => {
    const startTime = fmt(sub.start)
    const endTime = fmt(sub.end)

    switch (languageType) {
      case 'raw':
        ass += `Dialogue: 0,${startTime},${endTime},Raw,,0,0,0,,${sub.text}\n`
        break
      case 'translated':
        const translatedText = sub.translation || sub.text
        ass += `Dialogue: 0,${startTime},${endTime},Foreign,,0,0,0,,${translatedText}\n`
        break
      case 'both':
        ass += `Dialogue: 0,${startTime},${endTime},Raw,,0,0,0,,${sub.text}\n`
        if (sub.translation) {
          ass += `Dialogue: 0,${startTime},${endTime},Foreign,,0,0,0,,${sub.translation}\n`
        }
        break
    }
  })

  const suffix =
    languageType === 'raw' ? '_raw' : languageType === 'translated' ? '_translated' : ''
  downloadFile(ass, `${props.videoName || 'subtitles'}${suffix}.ass`, 'text/ass')
  successNotify(t('assExportSuccess'))
}

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  tryInit(props.id) // 首次挂载时先试一次

  // Set up 2-second interval for current subtitle detection
  updateCurrentSubtitleInterval = window.setInterval(() => {
    updateCurrentSubtitle()
  }, 2000)

  // Initial check
  updateCurrentSubtitle()
})

onUnmounted(() => {
  if (updateCurrentSubtitleInterval) {
    window.clearInterval(updateCurrentSubtitleInterval)
  }
})

watch(
  () => props.id,
  (newId) => {
    tryInit(newId) // id 变化时再试
  },
)

// Watch currentTime changes for immediate response (in addition to 5-second interval)
watch(
  () => props.currentTime,
  () => {
    updateCurrentSubtitle()
  },
)

// Watch bilingualSubs changes to update refs
watch(
  () => bilingualSubs.value,
  () => {
    nextTick(() => {
      updateCurrentSubtitle()
    })
  },
  { deep: true },
)

async function tryInit(id: number) {
  if (id <= 0) return // 忽略 -1 / 0 / 无效 id

  // 使用视频的原始语言和用户界面语言（与SubtitlePanel.vue一致）
  const primaryLang = props.rawLang || 'zh' // 原文语言（视频原始语言）
  const foreignLang = locale.value as string // 译文语言（i18n locale）

  console.log('Loading subtitles with languages:', {
    primaryLang,
    foreignLang,
    rawLang: props.rawLang,
  })

  // 真正获取字幕
  try {
    rawSubtitle.value = await fetchSubtitle(id, primaryLang) // 原文字幕
    console.log('Raw subtitles loaded:', rawSubtitle.value.length, 'items')
  } catch (error) {
    console.warn(`Raw subtitles (${primaryLang}) not found:`, error)
    rawSubtitle.value = []
  }

  try {
    foreignSubtitle.value = await fetchSubtitle(id, foreignLang) // 译文字幕
    foreignTrackLoaded.value = true
    console.log('Translation subtitles loaded:', foreignSubtitle.value.length, 'items')
  } catch (error) {
    console.warn(`Translation subtitles (${foreignLang}) not found:`, error)
    foreignSubtitle.value = []
    foreignTrackLoaded.value = false
  }

  updateBlobTracks()
}

/** which subtitle row is highlighted/being edited **/
// 同时编辑 译文和原文字幕
const activeSubtitleIndex = ref<number | null>(null)
const editSubtitleIndex = ref<number | null>(null)

// Current subtitle detection and floating ball
const currentSubtitleIndex = ref<number | null>(null)
const showFloatingBall = ref(false)
const subtitleRefs: { [key: number]: HTMLElement } = {}
const subtitleListContainer = ref<HTMLElement | null>(null)
let updateCurrentSubtitleInterval: number | null = null

// Manual scroll detection
const isUserManualScrolling = ref(false)

// Language selection dialog
const showLanguageDialog = ref(false)
const pendingExportFormat = ref<string>('')

const emit = defineEmits<{
  (e: 'seek-time', t: number): void
  (e: 'update-bloburls', urls: (string | undefined)[]): void
  (e: 'subs-loaded', raw: Subtitle[], foreign: Subtitle[]): void
}>()

// Function to update subtitle timing from external sources (like waveform)
function updateSubtitleTiming(index: number, newStart: number, newEnd: number) {
  if (index >= 0 && index < rawSubtitle.value.length) {
    rawSubtitle.value[index].start = newStart
    rawSubtitle.value[index].end = newEnd
  }
  if (index >= 0 && index < foreignSubtitle.value.length) {
    foreignSubtitle.value[index].start = newStart
    foreignSubtitle.value[index].end = newEnd
  }
}

// Expose the function for parent component
defineExpose({
  updateSubtitleTiming,
})

/* build a fresh VTT every time the array changes */
// 1) WATCH THE RAW TRACK (index 0)
watch(
  () => rawSubtitle.value,
  () => {
    updateBlobTracks()
    console.log('emit update bloburls signal')
    emit('update-bloburls', blobUrls.value)
    emit('subs-loaded', rawSubtitle.value, foreignSubtitle.value)
  },
  { deep: true },
)
// 2) WATCH THE Foreign TRACK (index 1)
watch(
  () => foreignSubtitle.value,
  () => {
    updateBlobTracks()
    emit('update-bloburls', blobUrls.value)
    emit('subs-loaded', rawSubtitle.value, foreignSubtitle.value)
  },
  { deep: true },
)

function setActiveSubtitle(index: number) {
  // highlight the row

  activeSubtitleIndex.value = index
  console.log(index)
  console.log('activeSubtitleIndex.value', activeSubtitleIndex.value)
  // find the clicked subtitle safely
  const subtitle1 = rawSubtitle.value[index]
  // const subtitle2 = foreignSubtitle.value[index] // Removed unused variable
  if (!subtitle1) return // guard for out-of-range clicks

  // seek the player to that subtitle’s start time
  emit('seek-time', subtitle1.start)
}

// function isCurrentSubtitle(subtitle) {
//   return props.currentTime >= subtitle.start && props.currentTime <= subtitle.end
// }

function calculateCPS(subtitle: any) {
  if (!subtitle.text) return 0
  const duration = subtitle.end - subtitle.start
  if (duration <= 0) return 0

  // 判断是否为英文文本（检查是否主要包含英文字符）
  const englishChars = subtitle.text.match(/[a-zA-Z]/g)
  const totalChars = subtitle.text.replace(/\s/g, '').length
  const isEnglish = englishChars && englishChars.length / totalChars > 0.5

  let count: number
  if (isEnglish) {
    // 英文：按单词数计算
    const words = subtitle.text
      .trim()
      .split(/\s+/)
      .filter((word: string) => word.length > 0)
    count = words.length
  } else {
    // 中文等其他语言：按字符数计算（去除空格）
    count = subtitle.text.replace(/\s/g, '').length
  }

  return Math.round((count / duration) * 10) / 10
}

function getCharacterSpeedColor(speed: number) {
  if (speed <= 2.5) {
    return 'bg-green-50 text-green-700 border-green-200 dark:bg-green-600/20 dark:text-green-400 dark:border-green-500/30'
  }
  if (speed <= 3.0) {
    return 'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-600/20 dark:text-yellow-400 dark:border-yellow-500/30'
  }
  return 'bg-red-50 text-red-700 border-red-200 dark:bg-red-600/20 dark:text-red-400 dark:border-red-500/30'
}

function getSpeedUnit(text: string) {
  if (!text) return t('charsPerSecond')

  // 判断是否为英文文本（检查是否主要包含英文字符）
  const englishChars = text.match(/[a-zA-Z]/g)
  const totalChars = text.replace(/\s/g, '').length
  const isEnglish = englishChars && englishChars.length / totalChars > 0.5

  return isEnglish ? t('wordsPerSecond') : t('charsPerSecond')
}

async function saveSubtitle(index: number) {
  const rawCurrent = rawSubtitle.value[index]
  const foreignCurrent = foreignSubtitle.value[index]

  if (!rawCurrent) return

  const rawChanged =
    rawCurrent.text !== rawBeforeEdit.value ||
    rawCurrent.start !== rawStartBeforeEdit.value ||
    rawCurrent.end !== rawEndBeforeEdit.value
  const tranChanged = !!foreignCurrent && (
    foreignCurrent.text !== transBeforeEdit.value ||
    foreignCurrent.start !== transStartBeforeEdit.value ||
    foreignCurrent.end !== transEndBeforeEdit.value
  )

  // 只把有改动的字幕推到后端
  const primaryLang = props.rawLang || 'zh'
  const foreignLang = locale.value as string

  if (rawChanged) {
    await linkSubtitles(props.id, primaryLang, rawSubtitle.value)
  }
  if (tranChanged && shouldPersistForeignTrack()) {
    await linkSubtitles(props.id, foreignLang, foreignSubtitle.value)
    foreignTrackLoaded.value = true
  }

  editSubtitleIndex.value = null
}

function cancelEdit() {
  editSubtitleIndex.value = null
}

function addSubtitle() {
  // 查找离当前时间最近且大于当前时间的字幕开始时间
  let endTime: number

  const nextSubtitle = rawSubtitle.value.find((sub) => sub.start > props.currentTime)
  if (nextSubtitle) {
    const timeDiff = nextSubtitle.start - props.currentTime
    if (timeDiff <= 30) {
      endTime = nextSubtitle.start
    } else {
      // 时间差大于30秒，使用默认值
      endTime = Math.min(props.currentTime + 5, props.duration)
    }
  } else {
    // 没有找到下一个字幕，使用默认值
    endTime = Math.min(props.currentTime + 5, props.duration)
  }

  const newSubtitle = {
    start: props.currentTime,
    end: endTime,
    text: '',
  }
  const newForeignSubtitle = {
    start: props.currentTime,
    end: endTime,
    text: '',
  }
  rawSubtitle.value.push(newSubtitle)
  foreignSubtitle.value.push(newForeignSubtitle)

  // 排序后重新找到新字幕的索引
  rawSubtitle.value.sort((a, b) => a.start - b.start)
  foreignSubtitle.value.sort((a, b) => a.start - b.start)

  // 找到新添加字幕的索引
  const newIndex = rawSubtitle.value.findIndex(
    (sub) => sub.start === props.currentTime && sub.end === endTime,
  )
  activeSubtitleIndex.value = newIndex

  successNotify(t('subtitleAdded'))
}

async function deleteSubtitle(index: number) {
  // 1 actually remove the cue
  console.log('delete index :', index)
  rawSubtitle.value.splice(index, 1)
  foreignSubtitle.value.splice(index, 1)

  // 2 reset or shift any indices that depended on the old list
  if (activeSubtitleIndex.value === index) {
    activeSubtitleIndex.value = null
  } else if (activeSubtitleIndex.value !== null && activeSubtitleIndex.value > index) {
    activeSubtitleIndex.value-- // shift down by one
  }

  if (editSubtitleIndex.value === index) {
    editSubtitleIndex.value = null
  } else if (editSubtitleIndex.value !== null && editSubtitleIndex.value > index) {
    editSubtitleIndex.value--
  }

  // 3 persist changes to backend
  const primaryLang = props.rawLang || 'zh'
  const foreignLang = locale.value as string
  await linkSubtitles(props.id, primaryLang, rawSubtitle.value)
  if (shouldPersistForeignTrack()) {
    await linkSubtitles(props.id, foreignLang, foreignSubtitle.value)
    foreignTrackLoaded.value = true
  }
}

function toggleSelect(index: number) {
  const s = new Set(selectedIndices.value)
  if (s.has(index)) s.delete(index)
  else s.add(index)
  selectedIndices.value = s
}

async function batchDelete() {
  const indices = Array.from(selectedIndices.value).sort((a, b) => b - a) // 倒序删除
  for (const idx of indices) {
    rawSubtitle.value.splice(idx, 1)
    foreignSubtitle.value.splice(idx, 1)
  }
  selectedIndices.value = new Set()
  const primaryLang = props.rawLang || 'zh'
  const foreignLang = locale.value as string
  await linkSubtitles(props.id, primaryLang, rawSubtitle.value)
  if (shouldPersistForeignTrack()) {
    await linkSubtitles(props.id, foreignLang, foreignSubtitle.value)
    foreignTrackLoaded.value = true
  }
  successNotify(t('subtitlesDeleted', { count: indices.length }))
}

async function batchMerge() {
  if (selectedIndices.value.size < 2) return
  const indices = Array.from(selectedIndices.value).sort((a, b) => a - b) // 升序
  const first = rawSubtitle.value[indices[0]]
  const last = rawSubtitle.value[indices[indices.length - 1]]
  
  // 合并原文
  const mergedText = indices.map(i => rawSubtitle.value[i].text).join(' ')
  // 合并译文
  const mergedTrans = indices.map((i) => foreignSubtitle.value[i]?.text ?? '').join(' ')
  
  // 新字幕：start=第一条start，end=最后一条end
  const merged = { start: first.start, end: last.end, text: mergedText }
  const mergedForeign = { start: first.start, end: last.end, text: mergedTrans }
  
  // 从后往前删除选中项，在第一个位置插入合并结果
  const toDelete = [...indices].reverse()
  for (const idx of toDelete) {
    rawSubtitle.value.splice(idx, 1)
    foreignSubtitle.value.splice(idx, 1)
  }
  rawSubtitle.value.splice(indices[0], 0, merged)
  foreignSubtitle.value.splice(indices[0], 0, mergedForeign)
  
  selectedIndices.value = new Set()
  const primaryLang = props.rawLang || 'zh'
  const foreignLang = locale.value as string
  await linkSubtitles(props.id, primaryLang, rawSubtitle.value)
  if (shouldPersistForeignTrack()) {
    await linkSubtitles(props.id, foreignLang, foreignSubtitle.value)
    foreignTrackLoaded.value = true
  }
  successNotify(t('subtitlesMerged'))
}

const rawBeforeEdit = ref('') // 原文旧值
const transBeforeEdit = ref('') // 译文旧值
const rawStartBeforeEdit = ref(0)
const rawEndBeforeEdit = ref(0)
const transStartBeforeEdit = ref(0)
const transEndBeforeEdit = ref(0)

// 多选状态
const selectedIndices = ref<Set<number>>(new Set())
function startEdit(i: number) {
  const raw = rawSubtitle.value[i]
  if (!raw) return

  const foreign = showTranslatedEditor.value ? ensureForeignSubtitle(i) : foreignSubtitle.value[i]

  // 把当前字幕内容缓存下来
  rawBeforeEdit.value = raw.text
  transBeforeEdit.value = foreign?.text ?? ''
  rawStartBeforeEdit.value = raw.start
  rawEndBeforeEdit.value = raw.end
  transStartBeforeEdit.value = foreign?.start ?? raw.start
  transEndBeforeEdit.value = foreign?.end ?? raw.end
  editSubtitleIndex.value = i
}

// Current subtitle detection
function updateCurrentSubtitle() {
  const currentTime = props.currentTime
  let found = false

  for (let i = 0; i < bilingualSubs.value.length; i++) {
    const sub = bilingualSubs.value[i]
    if (currentTime >= sub.start && currentTime <= sub.end) {
      currentSubtitleIndex.value = sub.originalIndex
      found = true
      break
    }
  }

  if (!found) {
    currentSubtitleIndex.value = null
  }

  // Auto-scroll to current subtitle if not manually scrolling
  if (!isUserManualScrolling.value && currentSubtitleIndex.value !== null) {
    scrollToSubtitleSilently(currentSubtitleIndex.value)
  }

  // Check if current subtitle is visible
  checkFloatingBallVisibility()
}

// Check if current subtitle is in viewport
function checkFloatingBallVisibility() {
  if (currentSubtitleIndex.value === null || !subtitleListContainer.value) {
    showFloatingBall.value = false
    return
  }

  const currentSubtitleEl = subtitleRefs[currentSubtitleIndex.value]
  if (!currentSubtitleEl) {
    showFloatingBall.value = false
    return
  }

  const containerRect = subtitleListContainer.value.getBoundingClientRect()
  const subtitleRect = currentSubtitleEl.getBoundingClientRect()

  // Check if subtitle is fully visible within the container
  const isVisible =
    subtitleRect.top >= containerRect.top && subtitleRect.bottom <= containerRect.bottom

  showFloatingBall.value = !isVisible
}

// Scroll to subtitle silently (for auto-scroll)
function scrollToSubtitleSilently(index: number) {
  if (!subtitleListContainer.value) {
    return
  }

  const subtitleEl = subtitleRefs[index]
  if (!subtitleEl) {
    return
  }

  // Check if subtitle is already visible
  const containerRect = subtitleListContainer.value.getBoundingClientRect()
  const subtitleRect = subtitleEl.getBoundingClientRect()

  const isVisible =
    subtitleRect.top >= containerRect.top && subtitleRect.bottom <= containerRect.bottom

  if (!isVisible) {
    subtitleEl.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
      inline: 'nearest',
    })
  }
}

// Scroll to current subtitle (for floating ball click)
function scrollToCurrentSubtitle() {
  if (currentSubtitleIndex.value === null || !subtitleListContainer.value) {
    return
  }

  // Reset manual scroll status
  isUserManualScrolling.value = false

  const currentSubtitleEl = subtitleRefs[currentSubtitleIndex.value]
  if (!currentSubtitleEl) {
    return
  }

  // Scroll to the element
  currentSubtitleEl.scrollIntoView({
    behavior: 'smooth',
    block: 'center',
    inline: 'nearest',
  })

  // Hide floating ball after scrolling
  showFloatingBall.value = false

  // Briefly highlight the subtitle by making it active
  const previousActive = activeSubtitleIndex.value
  activeSubtitleIndex.value = currentSubtitleIndex.value

  // Reset to previous active after 1 second
  setTimeout(() => {
    activeSubtitleIndex.value = previousActive
  }, 1000)
}

// Handle manual scroll detection
function handleManualScroll() {
  // Set manual scrolling state - will persist until floating ball is clicked
  isUserManualScrolling.value = true
}

// const subtitleStyle = computed(() => ({
//   fontFamily: `'${subtitleFont.value}'`,
//   color: subtitleColor.value,
//   fontSize: `${subtitleSize.value}px`,
// }))

// function updateSubtitleStyle() {
//   try {
//     localStorage.setItem('subtitleFont', subtitleFont.value)
//     localStorage.setItem('subtitleColor', subtitleColor.value)
//     localStorage.setItem('subtitleSize', subtitleSize.value)
//   } catch (e) {
//     console.error('Failed to save subtitle preferences:', e)
//   }
// }
</script>

<style scoped>
@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in {
  animation: fade-in 0.3s ease forwards;
  opacity: 0;
}

/* Custom textarea styles */
:deep(.el-textarea__inner) {
  border: 1px solid var(--el-border-color) !important;
  border-radius: 0.5rem !important;
  transition: all 0.2s !important;
  font-family: inherit !important;
  padding: 0.75rem !important;
}

:deep(.el-textarea__inner:focus) {
  border-color: var(--el-color-primary) !important;
  box-shadow: 0 0 0 2px var(--el-color-primary-light-8) !important;
}

/* 自定义滚动条 - 与背景相融 */
.custom-scrollbar::-webkit-scrollbar {
  width: 8px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: color-mix(in srgb, var(--el-fill-color-light) 80%, transparent);
  border-radius: 4px;
  margin: 4px 0;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--el-text-color-placeholder) 50%, transparent);
  border-radius: 4px;
  border: 1px solid color-mix(in srgb, var(--el-border-color) 70%, transparent);
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: color-mix(in srgb, var(--el-text-color-secondary) 60%, transparent);
  border-color: color-mix(in srgb, var(--el-border-color-darker) 70%, transparent);
}

.custom-scrollbar::-webkit-scrollbar-thumb:active {
  background: var(--el-text-color-secondary);
}

:global(html.dark) .custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(30, 41, 59, 0.4);
}

:global(html.dark) .custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(71, 85, 105, 0.6);
  border-color: rgba(51, 65, 85, 0.3);
}

:global(html.dark) .custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(100, 116, 139, 0.8);
  border-color: rgba(71, 85, 105, 0.5);
}

:global(html.dark) .custom-scrollbar::-webkit-scrollbar-thumb:active {
  background: rgba(100, 116, 139, 1);
}
</style>
