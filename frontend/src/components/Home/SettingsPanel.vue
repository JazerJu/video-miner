<template>
  <div
    class="h-full flex flex-col bg-white border border-slate-200 rounded-lg shadow-2xl backdrop-blur-xl dark:bg-slate-900/80 dark:border-white/10"
  >
    <!-- Header -->
    <div class="flex items-center justify-between p-6 border-b border-slate-200 dark:border-white/10">
      <h3 class="text-xl font-semibold text-slate-900 dark:text-white">
        {{ currentTabLabel }}
      </h3>
    </div>

    <!-- Content Area -->
    <div class="flex-1 p-8 overflow-y-auto relative text-slate-600 dark:text-gray-300">
      <!-- Loading overlay -->
      <div
        v-if="loading"
        class="absolute inset-0 bg-white/75 flex items-center justify-center z-10 backdrop-blur-sm dark:bg-slate-950/75"
      >
        <div class="flex items-center space-x-2">
          <div
            class="inline-block w-6 h-6 border-2 border-teal-400 border-t-transparent rounded-full animate-spin"
          ></div>
          <span class="text-slate-600 dark:text-gray-300">{{ t('loadingSettings') }}</span>
        </div>
      </div>

      <!-- Model Settings -->
      <div v-if="activeTab === 'model'" class="space-y-6 max-w-3xl">
        <!-- 断句 LLM Section -->
        <div class="border-b border-slate-200 pb-6 dark:border-white/10">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold text-slate-800 dark:text-gray-100">{{ t('splitLLM') }}</h3>
            <el-switch
              v-model="settings.enableSplit"
              :active-text="t('enableLLMSplit')"
              :inactive-text="t('asrDirectSentence')"
            />
          </div>

          <div class="space-y-4" :class="{ 'opacity-50 pointer-events-none': !settings.enableSplit }">
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('modelProviderSelect') }}</label>
              <select
                v-model="settings.selectedModelProvider"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              >
                <option
                  v-for="provider in providerOptions"
                  :key="provider.value"
                  :value="provider.value"
                >
                  {{ provider.label }}
                </option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('apiKey') }}</label>
              <div class="flex items-center space-x-2">
                <el-input
                  v-model="splitApiKey"
                  type="password"
                  show-password
                  :placeholder="t('enterApiKey')"
                  class="flex-1"
                />
                <button
                  @click="copyToClipboard(splitApiKey)"
                  class="px-3 py-2 bg-slate-100 hover:bg-slate-200 rounded-md text-sm text-slate-700 whitespace-nowrap transition-colors dark:bg-white/10 dark:hover:bg-white/15 dark:text-gray-200"
                >
                  {{ t('copy') }}
                </button>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('baseUrl') }}</label>
              <input
                v-model="splitBaseUrl"
                type="url"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
                :placeholder="t('enterApiBaseUrl')"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300"> {{ t('modelName') }} </label>
              <input
                v-model="splitModel"
                type="text"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
                :placeholder="t('enterModelName')"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300"> {{ t('requestThreads') }} </label>
              <input
                v-model.number="settings.splitNumThreads"
                type="number"
                min="1"
                max="32"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
                :placeholder="t('concurrentRequests')"
              />
            </div>

            <div class="flex items-center justify-between">
              <el-switch
                v-model="settings.splitUseProxy"
                :active-text="t('useProxy')"
                :inactive-text="t('noProxy')"
              />
              <button
                @click="testSplitConnection"
                :disabled="splitTesting"
                class="px-4 py-2 text-sm bg-teal-500 text-white rounded hover:bg-teal-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {{ splitTesting ? t('testing') : t('testConnection') }}
              </button>
            </div>
          </div>
        </div>

        <!-- 翻译 LLM Section -->
        <div class="pt-4">
          <h3 class="text-lg font-semibold text-slate-800 mb-4 dark:text-gray-100">{{ t('translateLLM') }}</h3>

          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('modelProviderSelect') }}</label>
              <select
                v-model="settings.translateSelectedModelProvider"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              >
                <option
                  v-for="provider in providerOptions"
                  :key="provider.value"
                  :value="provider.value"
                >
                  {{ provider.label }}
                </option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('apiKey') }}</label>
              <div class="flex items-center space-x-2">
                <el-input
                  v-model="translateApiKey"
                  type="password"
                  show-password
                  :placeholder="t('enterApiKey')"
                  class="flex-1"
                />
                <button
                  @click="copyToClipboard(translateApiKey)"
                  class="px-3 py-2 bg-slate-100 hover:bg-slate-200 rounded-md text-sm text-slate-700 whitespace-nowrap transition-colors dark:bg-white/10 dark:hover:bg-white/15 dark:text-gray-200"
                >
                  {{ t('copy') }}
                </button>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('baseUrl') }}</label>
              <input
                v-model="translateBaseUrl"
                type="url"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
                :placeholder="t('enterApiBaseUrl')"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300"> {{ t('modelName') }} </label>
              <input
                v-model="translateModel"
                type="text"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
                :placeholder="t('enterModelName')"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300"> {{ t('requestThreads') }} </label>
              <input
                v-model.number="settings.translateNumThreads"
                type="number"
                min="1"
                max="32"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
                :placeholder="t('concurrentRequests')"
              />
            </div>

            <div class="flex items-center justify-between">
              <el-switch
                v-model="settings.translateUseProxy"
                :active-text="t('useProxy')"
                :inactive-text="t('noProxy')"
              />
              <button
                @click="testTranslateConnection"
                :disabled="translateTesting"
                class="px-4 py-2 text-sm bg-teal-500 text-white rounded hover:bg-teal-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {{ translateTesting ? t('testing') : t('testConnection') }}
              </button>
            </div>

            <div
              class="flex items-center space-x-3 mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg dark:bg-amber-500/10 dark:border-amber-400/20"
            >
              <el-checkbox v-model="settings.plainTranslate" />
              <div>
                <span class="text-sm font-medium text-amber-800 dark:text-amber-100">{{ t('enablePlainTranslation') }}</span>
                <p class="text-xs text-amber-700 mt-1 dark:text-amber-200/70">
                  {{ t('plainTranslationDesc') }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Interface Settings -->
      <div v-if="activeTab === 'interface'" class="space-y-6 max-w-3xl">
        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('interfaceLanguage') }}</label>
          <select
            v-model="settings.rawLanguage"
            class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
          >
            <option v-for="lang in languageOptions" :key="lang.value" :value="lang.value">
              {{ lang.label }}
            </option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('defaultTranslateLanguage') }}</label>
          <p class="text-xs text-slate-500 mb-2 dark:text-gray-400">{{ t('defaultTranslateLanguageDesc') }}</p>
          <select
            v-model="settings.defaultTranslateLang"
            class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
          >
            <option v-for="lang in languageOptions" :key="lang.value" :value="lang.value">
              {{ lang.label }}
            </option>
          </select>
        </div>
      </div>

      <!-- Subtitle Settings -->
      <div v-if="activeTab === 'subtitle'" class="space-y-6 max-w-3xl">
        <!-- Subtitle Type Switch -->
        <div>
          <label class="block text-sm font-medium text-slate-600 mb-3 dark:text-gray-300">{{ t('subtitleType') }}</label>
          <div class="flex bg-slate-100 rounded-lg p-1 border border-slate-200 dark:bg-gray-800/60 dark:border-white/10">
            <button
              @click="subtitleType = 'raw'"
              :class="[
                'flex-1 py-2 px-4 text-sm font-medium rounded-md transition-colors',
                subtitleType === 'raw'
                  ? 'bg-teal-500 text-white shadow-sm'
                  : 'text-slate-500 hover:text-slate-900 hover:bg-white dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-white/10',
              ]"
            >
              {{ t('originalSubtitle') }}
            </button>
            <button
              @click="subtitleType = 'foreign'"
              :class="[
                'flex-1 py-2 px-4 text-sm font-medium rounded-md transition-colors',
                subtitleType === 'foreign'
                  ? 'bg-teal-500 text-white shadow-sm'
                  : 'text-slate-500 hover:text-slate-900 hover:bg-white dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-white/10',
              ]"
            >
              {{ t('translatedSubtitleFull') }}
            </button>
          </div>
          <p class="mt-2 text-sm text-slate-500 dark:text-gray-400">
            {{ switchSubtitleNote }}
          </p>
        </div>

        <div class="grid grid-cols-2 gap-6">
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('fontFamily') }}</label>
            <select
              :value="currentSubtitleSettings.fontFamily"
              @input="
                updateCurrentSubtitleSettings(
                  'fontFamily',
                  ($event.target as HTMLSelectElement).value,
                )
              "
              class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
            >
              <option value="宋体">宋体</option>
              <option value="微软雅黑">微软雅黑</option>
              <option value="Arial">Arial</option>
              <option value="Times New Roman">Times New Roman</option>
              <option value="Helvetica">Helvetica</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300"
              >{{ t('fontSize') }}: {{ currentSubtitleSettings.fontSize }}px</label
            >
            <input
              type="range"
              :value="currentSubtitleSettings.fontSize"
              @input="
                updateCurrentSubtitleSettings(
                  'fontSize',
                  parseInt(($event.target as HTMLInputElement).value),
                )
              "
              min="12"
              max="48"
              class="w-full"
            />
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('previewText') }}</label>
          <input
            :value="currentSubtitleSettings.previewText"
            @input="
              updateCurrentSubtitleSettings(
                'previewText',
                ($event.target as HTMLInputElement).value,
              )
            "
            class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
            :placeholder="t('previewTextPlaceholder')"
          />
        </div>

        <div class="grid grid-cols-2 gap-6">
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('fontColor') }}</label>
            <div class="flex items-center space-x-2 mb-2">
              <span class="text-sm text-slate-500 dark:text-gray-400"
                >{{ t('currentColor') }}: {{ currentSubtitleSettings.fontColor }}</span
              >
              <input
                type="color"
                :value="currentSubtitleSettings.fontColor"
                @input="
                  updateCurrentSubtitleSettings(
                    'fontColor',
                    ($event.target as HTMLInputElement).value,
                  )
                "
                class="w-8 h-8 rounded border border-slate-300 bg-white dark:border-white/20 dark:bg-gray-800"
              />
            </div>
            <div class="flex space-x-2">
              <button
                v-for="color in colorPresets"
                :key="color"
                @click="updateCurrentSubtitleSettings('fontColor', color)"
                :style="{ backgroundColor: color }"
                class="w-6 h-6 rounded border-2 border-slate-300 dark:border-white/30"
              ></button>
            </div>
        </div>

        <div>
            <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('fontWeight') }}</label>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="weight in fontWeights"
                :key="weight.value"
                @click="updateCurrentSubtitleSettings('fontWeight', weight.value)"
                :class="[
                  'px-2 py-1 text-xs border rounded',
                  currentSubtitleSettings.fontWeight === weight.value
                    ? 'bg-teal-500 text-white border-teal-400'
                    : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100 hover:text-slate-900 dark:bg-gray-800/70 dark:text-gray-300 dark:border-white/10 dark:hover:bg-white/10 dark:hover:text-white',
                ]"
              >
                {{ weight.label }}
              </button>
            </div>
          </div>
        </div>

        <div>
          <div class="flex items-center justify-between mb-4">
            <span class="text-sm font-medium text-slate-600 dark:text-gray-300">{{ t('displaySettings') }}</span>
          </div>

          <div class="space-y-4">
            <!-- 字幕背景样式选择 -->
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('subtitleBackground') }}</label>
              <select
                v-model="backgroundStyleProxy"
                class="w-full px-3 py-2 bg-white border border-slate-300 rounded-md text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-400/70 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              >
                <option value="none">{{ t('noBackground') }}</option>
                <option value="semi-transparent">{{ t('semiTransparent') }}</option>
                <option value="solid">{{ t('solidBackground') }}</option>
              </select>
            </div>

            <!-- 距底边距离设置 -->
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('bottomDistance') }}</label>
              <div class="flex items-center space-x-3">
                <input
                  type="range"
                  v-model="bottomDistanceProxy"
                  min="20"
                  max="200"
                  step="10"
                  class="flex-1 h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700/70"
                />
                <span class="text-sm text-slate-500 min-w-[50px] dark:text-gray-400">{{ bottomDistanceProxy }}px</span>
              </div>
            </div>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('backgroundColor') }}</label>
          <input
            type="color"
            :value="currentSubtitleSettings.backgroundColor"
            @input="
              updateCurrentSubtitleSettings(
                'backgroundColor',
                ($event.target as HTMLInputElement).value,
              )
            "
            class="w-12 h-8 rounded border border-slate-300 bg-white dark:border-white/20 dark:bg-gray-800"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300"
            >{{ t('borderRadius') }}: {{ currentSubtitleSettings.borderRadius }}px</label
          >
          <input
            type="range"
            :value="currentSubtitleSettings.borderRadius"
            @input="
              updateCurrentSubtitleSettings(
                'borderRadius',
                parseInt(($event.target as HTMLInputElement).value),
              )
            "
            min="0"
            max="20"
            class="w-full"
          />
        </div>

        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <span class="text-sm text-slate-600 dark:text-gray-300"
              >{{ t('textShadow') }}: {{ textShadowStatus }}</span
            >
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                :checked="currentSubtitleSettings.textShadow"
                @change="
                  updateCurrentSubtitleSettings(
                    'textShadow',
                    ($event.target as HTMLInputElement).checked,
                  )
                "
                class="sr-only"
              />
              <div
                :class="[
                  'w-11 h-6 rounded-full transition-colors',
                  currentSubtitleSettings.textShadow ? 'bg-teal-500' : 'bg-slate-300 dark:bg-gray-600',
                ]"
              >
                <div
                  :class="[
                    'w-5 h-5 bg-slate-100 rounded-full shadow transform transition-transform',
                    currentSubtitleSettings.textShadow ? 'translate-x-5' : 'translate-x-0',
                  ]"
                ></div>
              </div>
            </label>
          </div>

          <!-- Text Stroke Controls -->
          <div class="flex items-center justify-between">
            <span class="text-sm text-slate-600 dark:text-gray-300"
              >{{ t('textStroke') }}: {{ textStrokeStatus }}</span
            >
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                :checked="currentSubtitleSettings.textStroke"
                @change="
                  updateCurrentSubtitleSettings(
                    'textStroke',
                    ($event.target as HTMLInputElement).checked,
                  )
                "
                class="sr-only"
              />
              <div
                :class="[
                  'w-11 h-6 rounded-full transition-colors',
                  currentSubtitleSettings.textStroke ? 'bg-cyan-500' : 'bg-slate-300 dark:bg-gray-600',
                ]"
              >
                <div
                  :class="[
                    'w-5 h-5 bg-slate-100 rounded-full shadow transform transition-transform',
                    currentSubtitleSettings.textStroke ? 'translate-x-5' : 'translate-x-0',
                  ]"
                ></div>
              </div>
            </label>
          </div>

          <!-- Text Stroke Color -->
          <div v-if="currentSubtitleSettings.textStroke" class="space-y-2">
            <label class="block text-sm font-medium text-slate-600 dark:text-gray-300">{{ t('strokeColor') }}</label>
            <div class="flex items-center gap-2">
              <input
                type="color"
                :value="currentSubtitleSettings.textStrokeColor"
                @input="
                  updateCurrentSubtitleSettings(
                    'textStrokeColor',
                    ($event.target as HTMLInputElement).value,
                  )
                "
                class="w-12 h-8 rounded cursor-pointer border border-slate-300 bg-white dark:border-white/20 dark:bg-gray-800"
              />
              <input
                type="text"
                :value="currentSubtitleSettings.textStrokeColor"
                @input="
                  updateCurrentSubtitleSettings(
                    'textStrokeColor',
                    ($event.target as HTMLInputElement).value,
                  )
                "
                class="flex-1 px-3 py-1 bg-white border border-slate-300 rounded text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
                placeholder="#000000"
              />
            </div>
          </div>

          <!-- Text Stroke Width -->
          <div v-if="currentSubtitleSettings.textStroke" class="space-y-2">
            <label class="block text-sm font-medium text-slate-600 dark:text-gray-300"
              >{{ t('strokeWidth') }}: {{ currentSubtitleSettings.textStrokeWidth }}px</label
            >
            <input
              type="range"
              :value="currentSubtitleSettings.textStrokeWidth"
              @input="
                updateCurrentSubtitleSettings(
                  'textStrokeWidth',
                  parseInt(($event.target as HTMLInputElement).value),
                )
              "
              min="1"
              max="5"
              class="w-full"
            />
          </div>
        </div>

        <!-- Preview Section -->
        <div class="space-y-6">
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('realtimePreview') }}</label>
            <div
              class="p-4 border-2 border-dashed border-slate-300 rounded-lg bg-slate-50 text-center dark:border-white/20 dark:bg-gray-800/70"
              :style="{
                fontFamily: currentSubtitleSettings.fontFamily,
                fontSize: currentSubtitleSettings.fontSize + 'px',
                color: currentSubtitleSettings.fontColor,
                fontWeight: currentSubtitleSettings.fontWeight,
                backgroundColor:
                  currentSubtitleSettings.backgroundStyle === 'solid'
                    ? currentSubtitleSettings.backgroundColor
                    : currentSubtitleSettings.backgroundStyle === 'semi-transparent'
                      ? currentSubtitleSettings.backgroundColor + '80'
                      : 'transparent',
                borderRadius: currentSubtitleSettings.borderRadius + 'px',
                textShadow: getPreviewTextShadow(
                  currentSubtitleSettings.textShadow,
                  currentSubtitleSettings.textStroke,
                  currentSubtitleSettings.textStrokeColor,
                  currentSubtitleSettings.textStrokeWidth,
                ),
              }"
            >
              {{ currentSubtitleSettings.previewText }}
            </div>
          </div>
          <p class="text-sm text-slate-500 text-center dark:text-gray-400">
            {{ previewEffectNote }}
          </p>
        </div>
      </div>

      <!-- Transcription Engine Settings -->
      <div v-if="activeTab === 'transcription'" class="space-y-6 max-w-3xl">
        <!-- Primary Engine Selection -->
        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('transcriptionEngine') }}</label>
          <select
            v-model="settings.transcriptionPrimaryEngine"
            class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
          >
            <option
              v-for="engine in allTranscriptionEngines"
              :key="engine.value"
              :value="engine.value"
            >
              {{ engine.label }}
            </option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('hotwordList') }}</label>
          <textarea
            v-model="settings.hotwords"
            rows="6"
            class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
            :placeholder="t('hotwordPlaceholder')"
          />
        </div>

        <!-- VAD Backend -->
        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">VAD Backend</label>
          <select
            v-model="settings.vadBackend"
            class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
          >
            <option value="silero">Silero VAD (default)</option>
            <option value="firered">FireRed VAD</option>
          </select>
        </div>

        <!-- FunASR-GGUF Info -->
        <div
          v-if="settings.transcriptionPrimaryEngine === 'funasr_gguf'"
          class="space-y-3 border-t border-slate-200 pt-4 dark:border-white/10"
        >
          <h4 class="text-md font-medium text-slate-800 dark:text-gray-100">
            {{ t('funasrGgufSettings') }}
          </h4>
          <div
            class="p-3 bg-slate-50 rounded-md border border-slate-200 dark:bg-gray-800/50 dark:border-white/10"
          >
            <p class="text-sm text-slate-700 dark:text-gray-200">
              {{ t('funasrGgufInfo') }}
            </p>
            <p class="text-xs text-slate-500 mt-1 dark:text-gray-400">
              {{ t('funasrGgufSpecs') }}
            </p>
          </div>
        </div>

        <!-- ElevenLabs Settings -->
        <div v-if="showElevenLabsSettings" class="space-y-4 border-t border-slate-200 pt-4 dark:border-white/10">
          <h4 class="text-md font-medium text-slate-800 dark:text-gray-100">{{ t('elevenlabsSettings') }}</h4>
          <input
            v-model="settings.transcriptionElevenlabsApiKey"
            type="password"
            :placeholder="t('enterElevenlabsApiKey')"
            class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
          />
        </div>
      </div>

      <!-- Media Credentials Settings -->
      <div v-if="activeTab === 'media'" class="space-y-6 max-w-3xl">
        <div>
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('bilibiliSessData') }}</label>
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
            <el-input
              v-model="settings.bilibiliSessData"
              type="password"
              show-password
              :placeholder="t('enterBilibiliSessData')"
              class="min-w-0 flex-1"
            />
            <button
              @click="copyToClipboard(settings.bilibiliSessData)"
              class="w-full px-3 py-2 bg-slate-100 hover:bg-slate-200 rounded-md text-sm text-slate-700 whitespace-nowrap transition-colors dark:bg-white/10 dark:hover:bg-white/15 dark:text-gray-200 sm:w-auto"
            >
              {{ t('copy') }}
            </button>
            <button
              @click="handleValidateBilibiliSessData"
              :disabled="bilibiliSessDataValidating || !settings.bilibiliSessData.trim()"
              class="w-full px-3 py-2 bg-teal-600 hover:bg-teal-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-md text-sm text-white whitespace-nowrap transition-colors sm:w-auto"
            >
              <span v-if="bilibiliSessDataValidating">{{ t('validating') }}</span>
              <span v-else>{{ t('saveAndValidateBilibiliSessData') }}</span>
            </button>
          </div>
          <p class="mt-2 text-sm text-slate-500 dark:text-gray-400">
            {{ t('bilibiliSessDataNote') }}
          </p>
          <div
            v-if="bilibiliSessDataStatus"
            class="mt-3 rounded-md border px-3 py-2 text-sm"
            :class="
              bilibiliSessDataStatus.validation?.valid
                ? 'border-green-200 bg-green-50 text-green-800 dark:border-green-500/30 dark:bg-green-500/10 dark:text-green-200'
                : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200'
            "
          >
            <div class="font-medium">{{ getBilibiliSessDataStatusText() }}</div>
            <div
              v-if="bilibiliSessDataStatus.validation?.username || bilibiliSessDataStatus.validation?.uid"
              class="mt-1 text-xs"
            >
              {{ t('bilibiliAccount') }}:
              <span v-if="bilibiliSessDataStatus.validation?.username">
                {{ bilibiliSessDataStatus.validation.username }}
              </span>
              <span v-if="bilibiliSessDataStatus.validation?.uid">
                (UID {{ bilibiliSessDataStatus.validation.uid }})
              </span>
            </div>
            <div v-if="bilibiliSessDataStatus.expires_at" class="mt-1 text-xs">
              {{ t('bilibiliSessDataExpiresAt') }}:
              {{ formatBilibiliSessDataTime(bilibiliSessDataStatus.expires_at) }}
            </div>
            <div
              v-if="
                bilibiliSessDataStatus.validation?.checked &&
                !bilibiliSessDataStatus.validation?.valid &&
                bilibiliSessDataStatus.validation?.message
              "
              class="mt-1 text-xs"
            >
              {{ t('bilibiliSessDataMessage') }}:
              {{ bilibiliSessDataStatus.validation.message }}
            </div>
          </div>
        </div>

        <!-- YouTube cookies.txt 管理 -->
        <div class="border-t border-slate-200 pt-6 mt-6 dark:border-white/10">
          <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">YouTube cookies.txt</label>
          <div class="flex items-center space-x-3">
            <label
              class="flex-1 flex items-center justify-center px-4 py-2.5 border-2 border-dashed border-slate-300 rounded-lg cursor-pointer hover:border-teal-400/70 hover:bg-teal-50 transition-colors dark:border-white/20 dark:hover:bg-teal-500/10"
              :class="{ 'border-teal-400 bg-teal-50 dark:bg-teal-500/10': cookiesUploading }"
            >
              <input
                type="file"
                accept=".txt"
                class="hidden"
                @change="handleCookiesUpload"
                :disabled="cookiesUploading"
              />
              <div v-if="cookiesUploading" class="flex items-center text-teal-600 dark:text-teal-300">
                <div
                  class="inline-block w-4 h-4 mr-2 border-2 border-teal-400 border-t-transparent rounded-full animate-spin"
                ></div>
                <span class="text-sm">{{ t('uploading') }}</span>
              </div>
              <div v-else class="flex items-center text-sm text-slate-600 dark:text-gray-300">
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                  />
                </svg>
                <span>{{
                  cookiesStatus?.exists ? t('clickOverwriteUploadCookies') : t('clickUploadCookies')
                }}</span>
              </div>
            </label>

            <!-- 修改时间信息按钮 -->
            <div class="relative">
              <button
                @mouseenter="cookiesHover = true"
                @mouseleave="cookiesHover = false"
                class="p-2 text-slate-500 hover:text-slate-900 rounded-md hover:bg-slate-100 transition-colors dark:text-gray-400 dark:hover:text-white dark:hover:bg-white/10"
                :title="t('viewCookiesInfo')"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </button>
              <!-- Hover 弹出信息 -->
              <div
                v-if="cookiesHover && cookiesStatus?.exists"
                class="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-xl p-3 z-50 min-w-[220px] dark:bg-gray-800 dark:border-white/10"
              >
                <p class="text-xs text-slate-500 mb-1 dark:text-gray-400">{{ t('fileModifiedTime') }}</p>
                <p class="text-sm font-medium text-slate-800 dark:text-gray-100">
                  {{ formatCookiesTime(cookiesStatus.last_modified!) }}
                </p>
                <p class="text-xs text-slate-500 mt-1 dark:text-gray-400">{{ cookiesStatus.file_size }} bytes</p>
              </div>
            </div>
          </div>
          <p class="mt-2 text-sm text-slate-500 dark:text-gray-400">
            {{ t('youtubeCookiesDescBefore') }}
            <a
              href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
              target="_blank"
              class="text-teal-600 hover:text-teal-500 hover:underline dark:text-teal-300 dark:hover:text-teal-200"
              >Get cookies.txt LOCALLY</a
            >
            {{ t('youtubeCookiesDescAfter') }}
          </p>
          <!-- 当前状态提示 -->
          <div v-if="cookiesStatus?.exists" class="mt-2 flex items-center text-xs text-teal-600 dark:text-teal-300">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M5 13l4 4L19 7"
              />
            </svg>
            {{ t('cookiesUploadedAt', { time: formatCookiesTime(cookiesStatus.last_modified!) }) }}
          </div>
        </div>

        <!-- 网络代理设置 -->
        <div class="border-t border-slate-200 pt-6 mt-6 dark:border-white/10">
          <h4 class="text-sm font-medium text-slate-600 mb-4 dark:text-gray-300">{{ t('networkProxySettings') }}</h4>
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">{{ t('proxyServerAddress') }}</label>
            <input
              v-model="settings.proxyUrl"
              type="text"
              class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
              :placeholder="t('proxyServerPlaceholder')"
            />
            <p class="mt-2 text-sm text-slate-500 dark:text-gray-400">
              {{ t('proxyDescBefore') }}
              <code class="bg-slate-100 text-slate-700 px-1 rounded dark:bg-white/10 dark:text-gray-200">HTTPS_PROXY</code>
              {{ t('proxyDescAfter') }}
            </p>
          </div>
          <div class="mt-4 space-y-3">
            <label class="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                v-model="settings.downloadUseProxy"
                class="w-4 h-4 text-teal-500 bg-white border-slate-300 rounded focus:ring-teal-500 focus:ring-offset-white dark:bg-gray-800 dark:border-gray-600 dark:focus:ring-offset-gray-900"
              />
              <span class="text-sm text-slate-600 dark:text-gray-300">{{ t('downloadUseProxyLabel') }}</span>
            </label>
            <label class="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                v-model="settings.biliDownloadUseProxy"
                class="w-4 h-4 text-teal-500 bg-white border-slate-300 rounded focus:ring-teal-500 focus:ring-offset-white dark:bg-gray-800 dark:border-gray-600 dark:focus:ring-offset-gray-900"
              />
              <span class="text-sm text-slate-600 dark:text-gray-300">{{ t('biliDownloadUseProxyLabel') }}</span>
            </label>
            <label class="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                v-model="settings.splitUseProxy"
                class="w-4 h-4 text-teal-500 bg-white border-slate-300 rounded focus:ring-teal-500 focus:ring-offset-white dark:bg-gray-800 dark:border-gray-600 dark:focus:ring-offset-gray-900"
              />
              <span class="text-sm text-slate-600 dark:text-gray-300">{{ t('splitUseProxyLabel') }}</span>
            </label>
            <label class="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                v-model="settings.translateUseProxy"
                class="w-4 h-4 text-teal-500 bg-white border-slate-300 rounded focus:ring-teal-500 focus:ring-offset-white dark:bg-gray-800 dark:border-gray-600 dark:focus:ring-offset-gray-900"
              />
              <span class="text-sm text-slate-600 dark:text-gray-300">{{ t('translateUseProxyLabel') }}</span>
            </label>
          </div>
        </div>

        <!-- yt-dlp 包管理 -->
        <div class="border-t border-slate-200 pt-6 mt-6 dark:border-white/10">
          <h4 class="text-sm font-medium text-slate-600 mb-4 dark:text-gray-300">{{ t('ytDlpManagement') }}</h4>

          <!-- 当前状态 -->
          <div v-if="ytDlpLoading" class="flex items-center py-4">
            <div
              class="inline-block w-5 h-5 border-2 border-teal-400 border-t-transparent rounded-full animate-spin mr-2"
            ></div>
            <span class="text-sm text-slate-500 dark:text-gray-400">{{ t('loading') }}</span>
          </div>
          <div v-else-if="ytDlpStatus" class="space-y-3 mb-6">
            <div class="grid grid-cols-2 gap-4">
              <div class="bg-slate-50 rounded-lg p-3 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
                <p class="text-xs text-slate-500 mb-1 dark:text-gray-400">{{ t('ytDlpVersion') }}</p>
                <p class="text-sm font-medium text-slate-800 dark:text-gray-100">{{ ytDlpStatus.yt_dlp_version }}</p>
              </div>
              <div class="bg-slate-50 rounded-lg p-3 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
                <p class="text-xs text-slate-500 mb-1 dark:text-gray-400">{{ t('ejsScript') }}</p>
                <p
                  class="text-sm font-medium"
                  :class="ytDlpStatus.ejs_version !== '未安装' ? 'text-teal-600 dark:text-teal-300' : 'text-red-600 dark:text-red-400'"
                >
                  {{ formatYtDlpComponentVersion(ytDlpStatus.ejs_version) }}
                </p>
              </div>
              <div class="bg-slate-50 rounded-lg p-3 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
                <p class="text-xs text-slate-500 mb-1 dark:text-gray-400">{{ t('nodeRuntime') }}</p>
                <p
                  class="text-sm font-medium"
                  :class="ytDlpStatus.node_available ? 'text-teal-600 dark:text-teal-300' : 'text-red-600 dark:text-red-400'"
                >
                  {{ ytDlpStatus.node_version }}
                </p>
              </div>
              <div class="bg-slate-50 rounded-lg p-3 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
                <p class="text-xs text-slate-500 mb-1 dark:text-gray-400">{{ t('nodeRequirement') }}</p>
                <p class="text-sm font-medium text-slate-800 dark:text-gray-100">
                  {{ ytDlpStatus.node_required_version }}
                </p>
              </div>
            </div>

            <!-- 环境异常提示 -->
            <div
              v-if="!ytDlpStatus.node_available"
              class="bg-amber-50 border border-amber-200 rounded-lg p-3 dark:bg-amber-500/10 dark:border-amber-400/20"
            >
              <p class="text-sm text-amber-700 dark:text-amber-200">
                {{ t('nodeUnavailableWarning') }}
              </p>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="space-y-3">
            <button
              @click="handleInstallDeps"
              :disabled="ytDlpInstalling"
              class="w-full px-4 py-2.5 text-sm font-medium text-white bg-teal-500 rounded-lg hover:bg-teal-400 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
            >
              <div
                v-if="ytDlpInstalling"
                class="inline-block w-4 h-4 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin"
              ></div>
              {{ ytDlpInstalling ? t('installing') : t('installYtDlpDeps') }}
            </button>
            <p class="text-xs text-slate-500 dark:text-gray-400">
              {{ t('installYtDlpDepsDesc') }}
            </p>

            <button
              @click="handleUpgrade"
              :disabled="ytDlpUpgrading"
              class="w-full px-4 py-2.5 text-sm font-medium text-white bg-cyan-500 rounded-lg hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
            >
              <div
                v-if="ytDlpUpgrading"
                class="inline-block w-4 h-4 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin"
              ></div>
              {{ ytDlpUpgrading ? t('checkingUpgrade') : t('checkUpgradeYtDlp') }}
            </button>
            <p class="text-xs text-slate-500 dark:text-gray-400">{{ t('checkUpgradeYtDlpDesc') }}</p>

            <button
              @click="loadYtDlpStatus"
              :disabled="ytDlpLoading"
              class="w-full px-4 py-2 text-sm text-slate-600 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-50 transition-colors dark:text-gray-300 dark:bg-white/10 dark:hover:bg-white/15"
            >
              {{ t('refreshStatus') }}
            </button>
          </div>
        </div>
      </div>

      <!-- API Token Management -->
      <div v-if="activeTab === 'apiToken'" class="space-y-6 max-w-3xl">
        <div class="bg-slate-50 rounded-lg p-5 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
          <div class="flex items-center justify-between mb-4">
            <div>
              <h3 class="text-lg font-semibold text-slate-800 dark:text-gray-100">{{ t('apiTokenManagement') }}</h3>
              <p class="text-sm text-slate-500 mt-1 dark:text-gray-400">{{ t('apiTokenDesc') }}</p>
            </div>
            <button
              @click="openGenerateDialog"
              class="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white text-sm rounded-lg transition-colors flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" /></svg>
              {{ t('generateToken') }}
            </button>
          </div>

          <!-- Token List -->
          <div v-if="tokenLoading" class="py-8 text-center text-sm text-slate-500 dark:text-gray-400">
            {{ t('loading') }}
          </div>
          <div v-else-if="apiTokens.length === 0" class="py-8 text-center text-sm text-slate-500 dark:text-gray-400">
            {{ t('noApiTokens') }}
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="(tk, idx) in apiTokens"
              :key="idx"
              class="flex items-center justify-between p-4 bg-white rounded-lg border border-slate-200 dark:bg-gray-900/40 dark:border-white/10"
            >
              <div class="flex items-center gap-3">
                <div class="flex items-center gap-1.5 font-mono text-sm text-slate-700 dark:text-gray-200">
                  <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg>
                  {{ tk.key }}
                </div>
                <span class="text-xs text-slate-400">{{ new Date(tk.created_at).toLocaleString() }}</span>
              </div>
              <button
                @click="openRevokeDialog()"
                class="px-3 py-1.5 text-xs text-red-600 hover:text-red-700 bg-red-50 hover:bg-red-100 rounded-md transition-colors dark:text-red-400 dark:bg-red-900/20 dark:hover:bg-red-900/30"
              >
                {{ t('revoke') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Video Understanding -->
      <div v-if="activeTab === 'videoUnderstanding'" class="space-y-6 max-w-3xl">
        <!-- Section 1: Local Models -->
        <div class="bg-slate-50 rounded-lg p-4 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
          <div class="flex items-center justify-between mb-4">
            <h4 class="text-sm font-medium text-slate-600 dark:text-gray-300">
              {{ t('vuLocalModels') }}
            </h4>
            <div class="flex items-center gap-2">
              <span class="text-xs text-slate-400 dark:text-gray-500">{{ t('useProxy') }}</span>
              <el-switch v-model="settings.vuDownloadUseProxy" size="small" />
            </div>
          </div>
          <div class="space-y-3">
            <div
              v-for="model in vuModels"
              :key="model.name"
              class="p-3 bg-white rounded-md border border-slate-200 transition-colors dark:bg-gray-900/50 dark:border-white/10"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <span class="text-sm font-medium text-slate-700 dark:text-gray-200">{{ model.label }}</span>
                  <div class="mt-1 text-xs text-slate-400">
                    {{ model.description }} &middot; {{ formatBytes(getVuModelTotalSize(model)) }}
                  </div>
                  <div
                    v-if="getVuDownloadedSize(model) > 0 && getVuStatus(model) !== 'downloaded'"
                    class="mt-0.5 text-xs text-slate-400"
                  >
                    {{ formatBytes(getVuDownloadedSize(model)) }} / {{ formatBytes(getVuModelTotalSize(model)) }}
                  </div>
                </div>
                <div class="flex shrink-0 flex-col items-end gap-2">
                  <div class="text-xs font-medium" :class="getVuStatusClass(model)">
                    {{ getVuStatusText(model) }}
                    <span v-if="getVuStatus(model) === 'downloaded'" class="text-green-500">&#10003;</span>
                  </div>
                  <div
                    v-if="getVuStatus(model) !== 'downloading'"
                    class="flex items-center gap-2"
                  >
                    <label class="text-xs text-slate-400 dark:text-gray-500">{{ t('vuDownloadFrom') }}</label>
                    <select
                      v-model="vuDownloadSources[model.name]"
                      class="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-700 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                    >
                      <option v-for="source in vuSourceOptions" :key="source.value" :value="source.value">
                        {{ source.label }}
                      </option>
                    </select>
                    <button
                      class="h-8 px-3 text-xs font-medium bg-teal-500 hover:bg-teal-400 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      @click="startVuDownload(model.name)"
                    >
                      {{ getVuDownloadButtonText(model) }}
                    </button>
                  </div>
                  <button
                    v-else
                    class="h-8 px-3 text-xs font-medium text-white bg-teal-500 rounded-md opacity-70 cursor-not-allowed"
                    disabled
                  >
                    {{ t('vuDownloading') }}
                  </button>
                </div>
              </div>
              <div
                v-if="getVuStatus(model) === 'downloading'"
                class="mt-3 w-full bg-slate-200 rounded-full h-1.5 overflow-hidden dark:bg-gray-700"
              >
                <div
                  class="bg-teal-500 h-1.5 rounded-full transition-all duration-300 animate-pulse"
                  :style="{ width: getVuProgressPercent(model) + '%' }"
                ></div>
              </div>
              <div
                v-if="getVuStatus(model) === 'downloading' && vuProgress[model.name]?.current_file"
                class="mt-1 text-xs text-slate-400 truncate"
              >
                {{ vuProgress[model.name]?.current_file }}
              </div>
            </div>
          </div>
        </div>

        <!-- Section 1b: Inference Parameters -->
        <div class="bg-slate-50 rounded-lg p-4 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
          <h4 class="text-sm font-medium text-slate-600 mb-4 dark:text-gray-300">
            {{ t('vuInferenceParams') }}
          </h4>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                {{ t('vuThinkingBudget') }}
              </label>
              <select
                v-model="settings.vuThinkingBudget"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              >
                <option value="low">{{ t('vuBudgetLow') }}</option>
                <option value="medium">{{ t('vuBudgetMedium') }}</option>
                <option value="high">{{ t('vuBudgetHigh') }}</option>
              </select>
              <p class="mt-1 text-xs text-slate-400 dark:text-gray-500">
                {{ t('vuThinkingBudgetDesc') }}
              </p>
            </div>
          </div>
        </div>

        <!-- Section 2: External Vision Corner Detection -->
        <div class="bg-slate-50 rounded-lg p-4 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
          <h4 class="text-sm font-medium text-slate-600 mb-4 dark:text-gray-300">
            {{ t('vuCornerDetection') }}
          </h4>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                {{ t('vuCornerProvider') }}
              </label>
              <select
                v-model="settings.vuCornerProvider"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              >
                <option value="gemini">OpenRouter (Gemini as default)</option>
                <option value="gemini_official">Gemini (Official)</option>
                <option value="mimo">MiMo</option>
                <option value="openai_compatible">OpenAI Compatible</option>
              </select>
            </div>
            <div class="flex items-center">
              <el-switch
                v-model="settings.vuCornerUseProxy"
                :active-text="t('useProxy')"
                :inactive-text="t('noProxy')"
              />
            </div>
            <!-- Coverage threshold -->
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                {{ t('vuCornerCoverage') }}
              </label>
              <div class="flex items-center gap-3">
                <input
                  v-model.number="settings.vuCornerCoverage"
                  type="range"
                  min="0.3"
                  max="1"
                  step="0.05"
                  class="flex-1 accent-teal-600"
                />
                <span class="text-sm font-medium text-slate-700 dark:text-gray-200 w-12 text-right">
                  {{ Math.round(settings.vuCornerCoverage * 100) }}%
                </span>
              </div>
              <p class="mt-1 text-xs text-slate-400 dark:text-gray-500">
                {{ t('vuCornerCoverageDesc') }}
              </p>
            </div>
            <template v-if="settings.vuCornerProvider === 'gemini'">
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  {{ t('apiKey') }}
                </label>
                <el-input
                  v-model="settings.vuCornerGeminiApiKey"
                  type="password"
                  show-password
                  :placeholder="t('enterApiKey')"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  {{ t('baseUrl') }}
                </label>
                <input
                  v-model="settings.vuCornerGeminiBaseUrl"
                  type="text"
                  placeholder="https://openrouter.ai/api/v1"
                  class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  Model
                </label>
                <input
                  v-model="settings.vuCornerGeminiModel"
                  type="text"
                  placeholder="google/gemini-2.5-flash"
                  class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                />
              </div>
            </template>
            <template v-if="settings.vuCornerProvider === 'gemini_official'">
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  {{ t('apiKey') }}
                </label>
                <el-input
                  v-model="settings.vuCornerGeminiOfficialApiKey"
                  type="password"
                  show-password
                  :placeholder="t('enterApiKey')"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  {{ t('baseUrl') }}
                </label>
                <input
                  v-model="settings.vuCornerGeminiOfficialBaseUrl"
                  type="text"
                  placeholder="https://generativelanguage.googleapis.com/v1beta/openai"
                  class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  Model
                </label>
                <input
                  v-model="settings.vuCornerGeminiOfficialModel"
                  type="text"
                  placeholder="gemini-2.5-flash"
                  class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                />
              </div>
            </template>
            <template v-if="settings.vuCornerProvider === 'mimo'">
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  {{ t('apiKey') }}
                </label>
                <el-input
                  v-model="settings.vuCornerMimoApiKey"
                  type="password"
                  show-password
                  :placeholder="t('enterApiKey')"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  {{ t('baseUrl') }}
                </label>
                <input
                  v-model="settings.vuCornerMimoBaseUrl"
                  type="text"
                  placeholder="https://token-plan-cn.xiaomimimo.com/v1"
                  class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  Model
                </label>
                <input
                  v-model="settings.vuCornerMimoModel"
                  type="text"
                  placeholder="mimo-v2.5"
                  class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                />
              </div>
            </template>
            <template v-if="settings.vuCornerProvider === 'openai_compatible'">
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  {{ t('apiKey') }}
                </label>
                <el-input
                  v-model="settings.vuCornerOpenaiApiKey"
                  type="password"
                  show-password
                  :placeholder="t('enterApiKey')"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  {{ t('baseUrl') }}
                </label>
                <input
                  v-model="settings.vuCornerOpenaiBaseUrl"
                  type="text"
                  class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                  Model
                </label>
                <input
                  v-model="settings.vuCornerOpenaiModel"
                  type="text"
                  class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                />
              </div>
            </template>
          </div>
        </div>

        <!-- Section 3: Summary Orchestration -->
        <div class="bg-slate-50 rounded-lg p-4 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
          <h4 class="text-sm font-medium text-slate-600 mb-4 dark:text-gray-300">
            {{ t('vuSummaryOrchestration') }}
          </h4>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                Provider
              </label>
              <select
                v-model="settings.vuSummaryProvider"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              >
                <option value="deepseek">DeepSeek</option>
                <option value="openai_compatible">OpenAI Compatible</option>
              </select>
            </div>
            <div class="flex items-center">
              <el-switch
                v-model="settings.vuSummaryUseProxy"
                :active-text="t('useProxy')"
                :inactive-text="t('noProxy')"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                {{ t('apiKey') }}
              </label>
              <el-input
                v-model="settings.vuSummaryApiKey"
                type="password"
                show-password
                :placeholder="t('enterApiKey')"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                {{ t('baseUrl') }}
              </label>
              <input
                v-model="settings.vuSummaryBaseUrl"
                type="text"
                :placeholder="summaryBaseUrlPlaceholder"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                Model
              </label>
              <input
                v-model="settings.vuSummaryModel"
                type="text"
                :placeholder="summaryModelPlaceholder"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              />
            </div>
          </div>
        </div>

        <!-- Section 4: Knowledge LLM -->
        <div class="bg-slate-50 rounded-lg p-4 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
          <h4 class="text-sm font-medium text-slate-600 mb-1 dark:text-gray-300">
            {{ t('vuKnowledgeLLM') }}
          </h4>
          <p class="text-xs text-slate-400 mb-4">{{ t('vuKnowledgeLLMDesc') }}</p>
          <div class="space-y-3">
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                Provider
              </label>
              <select
                v-model="settings.vuKnowledgeProvider"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              >
                <option value="doubao">{{ t('doubao') }}</option>
                <option value="step">StepFun</option>
                <option value="openrouter">OpenRouter</option>
                <option value="openai_compatible">OpenAI Compatible</option>
              </select>
            </div>
            <div class="flex items-center">
              <el-switch
                v-model="settings.vuKnowledgeUseProxy"
                :active-text="t('useProxy')"
                :inactive-text="t('noProxy')"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                {{ t('apiKey') }}
              </label>
              <el-input
                v-model="settings.vuKnowledgeApiKey"
                type="password"
                show-password
                :placeholder="t('enterApiKey')"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                {{ t('baseUrl') }}
              </label>
              <input
                v-model="settings.vuKnowledgeBaseUrl"
                type="text"
                :placeholder="knowledgeBaseUrlPlaceholder"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-600 mb-2 dark:text-gray-300">
                Model
              </label>
              <input
                v-model="settings.vuKnowledgeModel"
                type="text"
                :placeholder="knowledgeModelPlaceholder"
                class="w-full p-2 bg-white border border-slate-300 rounded-md text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Tags Management -->
      <div v-if="activeTab === 'tags'" class="space-y-6 max-w-3xl">
        <!-- Create New Tag -->
        <div class="bg-slate-50 rounded-lg p-4 border border-slate-200 dark:bg-gray-800/50 dark:border-white/10">
          <h4 class="text-sm font-medium text-slate-600 mb-3 dark:text-gray-300">{{ t('createNewTag') }}</h4>
          <div class="flex items-center space-x-3">
            <input
              v-model="newTagName"
              type="text"
              class="flex-1 p-2 bg-white border border-slate-300 rounded-md text-slate-900 placeholder-slate-400 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100 dark:placeholder-gray-500"
              :placeholder="t('enterTagName')"
              @keyup.enter="createNewTag"
            />
            <div class="flex items-center space-x-2">
              <input
                v-model="newTagColor"
                type="color"
                class="w-10 h-10 rounded border border-slate-300 bg-white cursor-pointer dark:border-white/20 dark:bg-gray-800"
              />
              <span class="text-sm text-slate-500 dark:text-gray-400">{{ newTagColor }}</span>
            </div>
            <button
              @click="createNewTag"
              :disabled="!newTagName.trim() || creatingTag"
              class="px-4 py-2 bg-teal-500 text-white rounded hover:bg-teal-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {{ creatingTag ? t('creating') : t('create') }}
            </button>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <span class="text-xs font-medium text-slate-500 dark:text-gray-400">{{ t('recommendedColors') }}</span>
            <button
              v-for="color in tagColorPresets"
              :key="`new-${color}`"
              type="button"
              class="h-7 w-7 rounded-full border-2 transition hover:scale-105"
              :class="
                newTagColor === color
                  ? 'border-cyan-200 ring-2 ring-cyan-400/40'
                  : 'border-slate-300 shadow-sm dark:border-white/70'
              "
              :style="{ backgroundColor: color }"
              @click="newTagColor = color"
            />
            <button
              type="button"
              class="rounded-full border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:border-teal-400/60 hover:text-slate-900 hover:bg-slate-100 dark:border-white/15 dark:text-gray-300 dark:hover:text-white dark:hover:bg-white/10"
              @click="newTagColor = getRandomTagColor()"
            >
              {{ t('random') }}
            </button>
          </div>
        </div>

        <!-- Tags List -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-medium text-slate-600 dark:text-gray-300">{{ t('tagList') }} ({{ tags.length }})</h4>
            <div v-if="selectedTagIds.length > 0" class="flex items-center space-x-2">
              <span class="text-sm text-slate-500 dark:text-gray-400">{{ t('selectedTagCount', { count: selectedTagIds.length }) }}</span>
              <button
                @click="batchDeleteTags"
                class="px-3 py-1 bg-red-500 text-white text-sm rounded hover:bg-red-600"
              >
                {{ t('batchDelete') }}
              </button>
              <button
                @click="selectedTagIds = []"
                class="px-3 py-1 bg-slate-100 text-slate-600 text-sm rounded hover:bg-slate-200 hover:text-slate-900 transition-colors dark:bg-white/10 dark:text-gray-300 dark:hover:bg-white/15 dark:hover:text-white"
              >
                {{ t('cancel') }}
              </button>
            </div>
          </div>

          <div v-if="loadingTags" class="flex items-center justify-center py-8">
            <div
              class="inline-block w-6 h-6 border-2 border-teal-400 border-t-transparent rounded-full animate-spin"
            ></div>
            <span class="ml-2 text-slate-500 dark:text-gray-400">{{ t('loading') }}</span>
          </div>

          <div v-else-if="tags.length === 0" class="text-center py-8 text-slate-500 dark:text-gray-400">
            {{ t('noTagsCreateHint') }}
          </div>

          <div v-else class="space-y-2 max-h-96 overflow-y-auto">
            <div
              v-for="tag in tags"
              :key="tag.id"
              class="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200 hover:border-teal-400/40 transition-colors dark:bg-gray-800/50 dark:border-white/10"
            >
              <div class="flex items-center space-x-3">
                <input
                  type="checkbox"
                  :checked="selectedTagIds.includes(tag.id)"
                  @change="toggleTagSelection(tag.id)"
                  class="w-4 h-4 text-teal-500 bg-white border-slate-300 rounded focus:ring-teal-500 focus:ring-offset-white dark:bg-gray-800 dark:border-gray-600 dark:focus:ring-offset-gray-900"
                />
                <span
                  class="px-2 py-1 rounded text-sm font-medium"
                  :style="{ backgroundColor: tag.color + '20', color: tag.color }"
                >
                  {{ tag.name }}
                </span>
              </div>
              <div class="flex items-center space-x-2">
                <!-- Edit Mode -->
                <template v-if="editingTagId === tag.id">
                  <input
                    v-model="editingTagName"
                    type="text"
                    class="w-24 p-1 text-sm bg-white border border-slate-300 rounded text-slate-900 focus:outline-none focus:border-teal-400/70 focus:ring-2 focus:ring-teal-500/20 dark:bg-gray-800/70 dark:border-white/10 dark:text-gray-100"
                    @keyup.enter="saveTagEdit(tag)"
                  />
                  <input
                    v-model="editingTagColor"
                    type="color"
                    class="w-8 h-8 rounded cursor-pointer border border-slate-300 bg-white dark:border-white/20 dark:bg-gray-800"
                  />
                  <div
                    class="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 dark:border-white/10 dark:bg-gray-800/60"
                  >
                    <button
                      v-for="color in tagColorPresets"
                      :key="`edit-${tag.id}-${color}`"
                      type="button"
                      class="h-5 w-5 rounded-full border transition hover:scale-105"
                      :class="
                        editingTagColor === color
                          ? 'border-cyan-200 ring-1 ring-cyan-400/50'
                          : 'border-slate-300 dark:border-white/70'
                      "
                      :style="{ backgroundColor: color }"
                      @click="editingTagColor = color"
                    />
                  </div>
                  <button @click="saveTagEdit(tag)" class="p-1 text-teal-600 hover:text-teal-500 dark:text-teal-300 dark:hover:text-teal-200">
                    ✓
                  </button>
                  <button @click="cancelTagEdit" class="p-1 text-slate-500 hover:text-slate-700 dark:text-gray-400 dark:hover:text-gray-200">
                    ✕
                  </button>
                </template>
                <template v-else>
                  <button
                    @click="startTagEdit(tag)"
                    class="p-1 text-slate-500 hover:text-teal-600 dark:text-gray-400 dark:hover:text-teal-300"
                    :title="t('edit')"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                      ></path>
                    </svg>
                  </button>
                  <button
                    @click="deleteSingleTag(tag)"
                    class="p-1 text-slate-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-500"
                    :title="t('delete')"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      ></path>
                    </svg>
                  </button>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div
      class="flex justify-end space-x-3 p-4 border-t border-slate-200 bg-slate-50/90 rounded-b-lg dark:border-white/10 dark:bg-gray-900/70"
    >
      <button
        @click="resetSettings"
        :disabled="loading || saving"
        class="px-4 py-2 text-sm text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed dark:text-gray-400 dark:hover:text-white dark:hover:bg-white/10"
      >
        {{ t('resetToDefault') }}
      </button>
      <button
        @click="saveSettings"
        :disabled="loading || saving"
        class="px-4 py-2 text-sm text-white bg-teal-500 rounded hover:bg-teal-400 disabled:opacity-50 disabled:cursor-not-allowed flex items-center transition-colors"
      >
        <span
          v-if="saving"
          class="inline-block w-4 h-4 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin"
        ></span>
        {{ saving ? t('saving') : t('saveSettings') }}
      </button>
    </div>

    <!-- Token Credentials Dialog -->
    <div
      v-if="tokenCredsDialog"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="tokenCredsDialog = false"
    >
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-md border border-slate-200 dark:border-white/10 shadow-2xl">
        <h3 class="text-lg font-semibold text-slate-800 mb-4 dark:text-gray-100">
          {{ tokenCredsMode === 'generate' ? t('generateToken') : t('revokeToken') }}
        </h3>
        <p class="text-sm text-slate-500 mb-4 dark:text-gray-400">{{ t('reEnterCredentials') }}</p>
        <div class="space-y-3">
          <input
            v-model="tokenCredsUsername"
            type="text"
            :placeholder="t('username')"
            class="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:bg-gray-900/50 dark:border-white/10 dark:text-gray-100"
            @keyup.enter="submitTokenCreds"
          />
          <input
            v-model="tokenCredsPassword"
            type="password"
            :placeholder="t('password')"
            class="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:bg-gray-900/50 dark:border-white/10 dark:text-gray-100"
            @keyup.enter="submitTokenCreds"
          />
        </div>
        <div class="flex justify-end gap-3 mt-6">
          <button @click="tokenCredsDialog = false" class="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 dark:text-gray-400 dark:hover:text-gray-200">
            {{ t('cancel') }}
          </button>
          <button @click="submitTokenCreds" class="px-4 py-2 text-sm text-white bg-teal-600 hover:bg-teal-700 rounded-lg transition-colors">
            {{ t('confirm') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Token Result Dialog (one-time display) -->
    <div
      v-if="tokenResultDialog"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="closeTokenResult"
    >
      <div class="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-lg border border-slate-200 dark:border-white/10 shadow-2xl">
        <div class="flex items-center gap-2 mb-3">
          <svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <h3 class="text-lg font-semibold text-slate-800 dark:text-gray-100">{{ t('tokenGenerated') }}</h3>
        </div>
        <p class="text-sm text-amber-600 mb-4 dark:text-amber-400">{{ t('tokenCopyWarning') }}</p>
        <div class="flex items-center gap-2">
          <code class="flex-1 px-3 py-2 bg-slate-100 dark:bg-gray-900/60 rounded-lg text-sm font-mono text-slate-700 dark:text-gray-200 break-all">
            {{ tokenResultValue }}
          </code>
          <button @click="copyToken" class="px-3 py-2 text-sm text-white bg-teal-600 hover:bg-teal-700 rounded-lg transition-colors whitespace-nowrap">
            {{ t('copy') }}
          </button>
        </div>
        <div class="flex justify-end mt-6">
          <button @click="closeTokenResult" class="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 dark:text-gray-400 dark:hover:text-gray-200">
            {{ t('close') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  loadConfig,
  saveConfig,
  loadUserHiddenCategories,
  saveUserHiddenCategories,
  type FrontendSettings,
  BACKEND,
  loadVidUnderModels,
  downloadVidUnderModel,
  getVidUnderDownloadProgress,
  formatBytes,
  type VidUnderModel,
  type VidUnderProgress,
  type VidUnderModelSource,
  type VidUnderModelStatus,
  validateBilibiliSessData,
  type BilibiliSessDataStatus,
} from '@/composables/ConfigAPI'
import { ElMessageBox } from 'element-plus'
import { ElMessage } from '@/composables/useNotification'
import { useSubtitleStyle } from '@/composables/SubtitleStyle'
import {
  loadTags,
  createTag,
  updateTag,
  deleteTag,
  batchDeleteTags as batchDeleteTagsAPI,
  type Tag,
} from '@/composables/TagsAPI'
import { TAG_COLOR_PRESETS, getDistinctTagColor, getRandomTagColor } from '@/composables/TagColors'
import {
  getYtDlpStatus,
  installYtDlpDeps,
  upgradeYtDlp,
  type YtDlpStatus,
} from '@/composables/YtDlpAPI'
import {
  getYoutubeCookiesStatus,
  uploadYoutubeCookies,
  type CookiesStatus,
} from '@/composables/CookiesAPI'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  activeTab: string
  categories?: Array<{ id: number; name: string; items?: any[] }>
}>()

const emit = defineEmits<{
  (e: 'categories-updated'): void
}>()

// 使用字幕样式composable
const { updateSubtitleSettings, updateForeignSubtitleSettings } = useSubtitleStyle()

// i18n functionality
const { t, locale } = useI18n()

// 字幕类型选择
const subtitleType = ref<'raw' | 'foreign'>('raw')

// 背景样式代理属性
const backgroundStyleProxy = computed({
  get() {
    return subtitleType.value === 'raw' ? settings.backgroundStyle : settings.foreignBackgroundStyle
  },
  set(value: 'none' | 'solid' | 'semi-transparent') {
    if (subtitleType.value === 'raw') {
      settings.backgroundStyle = value
    } else {
      settings.foreignBackgroundStyle = value
    }
  },
})

// 距底边距离代理属性
const bottomDistanceProxy = computed({
  get() {
    return subtitleType.value === 'raw' ? settings.bottomDistance : settings.foreignBottomDistance
  },
  set(value: number) {
    if (subtitleType.value === 'raw') {
      settings.bottomDistance = value
    } else {
      settings.foreignBottomDistance = value
    }
  },
})

// 断句LLM的API密钥和基础URL计算属性
const splitApiKey = computed({
  get() {
    switch (settings.selectedModelProvider) {
      case 'deepseek':
        return settings.deepseekApiKey
      case 'openai':
        return settings.openaiApiKey
      case 'qwen':
        return settings.qwenApiKey
      case 'ollama':
        return settings.ollamaApiKey || ''
      case 'local':
        return settings.localApiKey || ''
      case 'moonshot':
        return settings.moonshotApiKey || ''
      case 'volcano':
        return settings.volcanoApiKey || ''
      case 'openrouter':
        return settings.openrouterApiKey || ''
      case 'cerebras':
        return settings.cerebrasApiKey || ''
      default:
        return settings.deepseekApiKey
    }
  },
  set(value: string) {
    switch (settings.selectedModelProvider) {
      case 'deepseek':
        settings.deepseekApiKey = value
        break
      case 'openai':
        settings.openaiApiKey = value
        break
      case 'qwen':
        settings.qwenApiKey = value
        break
      case 'ollama':
        settings.ollamaApiKey = value
        break
      case 'local':
        settings.localApiKey = value
        break
      case 'moonshot':
        settings.moonshotApiKey = value
        break
      case 'volcano':
        settings.volcanoApiKey = value
        break
      case 'openrouter':
        settings.openrouterApiKey = value
        break
      case 'cerebras':
        settings.cerebrasApiKey = value
        break
    }
  },
})

const summaryBaseUrlPlaceholder = computed(() => {
  switch (settings.vuSummaryProvider) {
    case 'deepseek': return 'https://api.deepseek.com'
    default: return ''
  }
})

const summaryModelPlaceholder = computed(() => {
  switch (settings.vuSummaryProvider) {
    case 'deepseek': return 'deepseek-chat'
    default: return ''
  }
})

const knowledgeBaseUrlPlaceholder = computed(() => {
  switch (settings.vuKnowledgeProvider) {
    case 'doubao': return 'https://ark.cn-beijing.volces.com/api/v3'
    case 'step': return 'https://api.stepfun.com/v1'
    case 'openrouter': return 'https://openrouter.ai/api/v1'
    default: return ''
  }
})

const knowledgeModelPlaceholder = computed(() => {
  switch (settings.vuKnowledgeProvider) {
    case 'doubao': return 'doubao-seed-2-0-pro-260215'
    case 'step': return 'step-3.7-flash'
    case 'openrouter': return 'google/gemini-2.5-flash'
    default: return ''
  }
})

const splitBaseUrl = computed({
  get() {
    switch (settings.selectedModelProvider) {
      case 'deepseek':
        return settings.deepseekBaseUrl
      case 'openai':
        return settings.openaiBaseUrl
      case 'qwen':
        return settings.qwenBaseUrl
      case 'ollama':
        return settings.ollamaBaseUrl || 'http://127.0.0.1:11434'
      case 'local':
        return settings.localBaseUrl || 'http://localhost:1234/v1'
      case 'moonshot':
        return settings.moonshotBaseUrl || 'https://api.moonshot.cn/v1'
      case 'volcano':
        return settings.volcanoBaseUrl || 'https://ark.cn-beijing.volces.com/api/v3'
      case 'openrouter':
        return settings.openrouterBaseUrl || 'https://openrouter.ai/api/v1'
      case 'cerebras':
        return settings.cerebrasBaseUrl || 'https://api.cerebras.ai/v1'
      default:
        return settings.deepseekBaseUrl
    }
  },
  set(value: string) {
    switch (settings.selectedModelProvider) {
      case 'deepseek':
        settings.deepseekBaseUrl = value
        break
      case 'openai':
        settings.openaiBaseUrl = value
        break
      case 'qwen':
        settings.qwenBaseUrl = value
        break
      case 'ollama':
        settings.ollamaBaseUrl = value
        break
      case 'local':
        settings.localBaseUrl = value
        break
      case 'moonshot':
        settings.moonshotBaseUrl = value
        break
      case 'volcano':
        settings.volcanoBaseUrl = value
        break
      case 'openrouter':
        settings.openrouterBaseUrl = value
        break
      case 'cerebras':
        settings.cerebrasBaseUrl = value
        break
    }
  },
})

// 翻译LLM的API密钥和基础URL计算属性
const translateApiKey = computed({
  get() {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek':
        return settings.translateDeepseekApiKey
      case 'openai':
        return settings.translateOpenaiApiKey
      case 'qwen':
        return settings.translateQwenApiKey
      case 'ollama':
        return settings.translateOllamaApiKey || ''
      case 'local':
        return settings.translateLocalApiKey || ''
      case 'moonshot':
        return settings.translateMoonshotApiKey || ''
      case 'volcano':
        return settings.translateVolcanoApiKey || ''
      case 'openrouter':
        return settings.translateOpenrouterApiKey || ''
      case 'cerebras':
        return settings.translateCerebrasApiKey || ''
      default:
        return settings.translateDeepseekApiKey
    }
  },
  set(value: string) {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek':
        settings.translateDeepseekApiKey = value
        break
      case 'openai':
        settings.translateOpenaiApiKey = value
        break
      case 'qwen':
        settings.translateQwenApiKey = value
        break
      case 'ollama':
        settings.translateOllamaApiKey = value
        break
      case 'local':
        settings.translateLocalApiKey = value
        break
      case 'moonshot':
        settings.translateMoonshotApiKey = value
        break
      case 'volcano':
        settings.translateVolcanoApiKey = value
        break
      case 'openrouter':
        settings.translateOpenrouterApiKey = value
        break
      case 'cerebras':
        settings.translateCerebrasApiKey = value
        break
    }
  },
})

const translateBaseUrl = computed({
  get() {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek':
        return settings.translateDeepseekBaseUrl
      case 'openai':
        return settings.translateOpenaiBaseUrl
      case 'qwen':
        return settings.translateQwenBaseUrl
      case 'ollama':
        return settings.translateOllamaBaseUrl || 'http://127.0.0.1:11434'
      case 'local':
        return settings.translateLocalBaseUrl || 'http://localhost:1234/v1'
      case 'moonshot':
        return settings.translateMoonshotBaseUrl || 'https://api.moonshot.cn/v1'
      case 'volcano':
        return settings.translateVolcanoBaseUrl || 'https://ark.cn-beijing.volces.com/api/v3'
      case 'openrouter':
        return settings.translateOpenrouterBaseUrl || 'https://openrouter.ai/api/v1'
      case 'cerebras':
        return settings.translateCerebrasBaseUrl || 'https://api.cerebras.ai/v1'
      default:
        return settings.translateDeepseekBaseUrl
    }
  },
  set(value: string) {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek':
        settings.translateDeepseekBaseUrl = value
        break
      case 'openai':
        settings.translateOpenaiBaseUrl = value
        break
      case 'qwen':
        settings.translateQwenBaseUrl = value
        break
      case 'ollama':
        settings.translateOllamaBaseUrl = value
        break
      case 'local':
        settings.translateLocalBaseUrl = value
        break
      case 'moonshot':
        settings.translateMoonshotBaseUrl = value
        break
      case 'volcano':
        settings.translateVolcanoBaseUrl = value
        break
      case 'openrouter':
        settings.translateOpenrouterBaseUrl = value
        break
      case 'cerebras':
        settings.translateCerebrasBaseUrl = value
        break
    }
  },
})

// 当前字幕设置的计算属性
const currentSubtitleSettings = computed(() => {
  if (subtitleType.value === 'raw') {
    return {
      fontFamily: settings.fontFamily,
      previewText: settings.previewText,
      fontColor: settings.fontColor,
      fontSize: settings.fontSize,
      fontWeight: settings.fontWeight,
      backgroundColor: settings.backgroundColor,
      borderRadius: settings.borderRadius,
      textShadow: settings.textShadow,
      textStroke: settings.textStroke,
      textStrokeColor: settings.textStrokeColor,
      textStrokeWidth: settings.textStrokeWidth,
      backgroundStyle: settings.backgroundStyle,
      bottomDistance: settings.bottomDistance,
    }
  } else {
    return {
      fontFamily: settings.foreignFontFamily,
      previewText: settings.foreignPreviewText,
      fontColor: settings.foreignFontColor,
      fontSize: settings.foreignFontSize,
      fontWeight: settings.foreignFontWeight,
      backgroundColor: settings.foreignBackgroundColor,
      borderRadius: settings.foreignBorderRadius,
      textShadow: settings.foreignTextShadow,
      textStroke: settings.foreignTextStroke,
      textStrokeColor: settings.foreignTextStrokeColor,
      textStrokeWidth: settings.foreignTextStrokeWidth,
      backgroundStyle: settings.foreignBackgroundStyle,
      bottomDistance: settings.foreignBottomDistance,
    }
  }
})

const currentSubtitleTypeLabel = computed(() =>
  t(subtitleType.value === 'raw' ? 'original' : 'foreign'),
)
const switchSubtitleNote = computed(() =>
  t('switchSubtitleNote', { type: currentSubtitleTypeLabel.value }),
)
const previewEffectNote = computed(() =>
  t('previewEffectNote', { type: currentSubtitleTypeLabel.value }),
)
const textShadowStatus = computed(() =>
  t(currentSubtitleSettings.value.textShadow ? 'enableShadow' : 'disableShadow'),
)
const textStrokeStatus = computed(() =>
  t(currentSubtitleSettings.value.textStroke ? 'enableStroke' : 'disableStroke'),
)

// 更新当前字幕设置的方法
const updateCurrentSubtitleSettings = (key: string, value: any) => {
  if (subtitleType.value === 'raw') {
    ;(settings as any)[key] = value
  } else {
    ;(settings as any)[`foreign${key.charAt(0).toUpperCase()}${key.slice(1)}`] = value
  }
}

// 生成预览用的组合文字阴影和描边效果
const getPreviewTextShadow = (
  textShadow: boolean,
  textStroke: boolean,
  strokeColor: string,
  strokeWidth: number,
) => {
  const effects = []

  // 添加描边效果
  if (textStroke) {
    for (let x = -strokeWidth; x <= strokeWidth; x++) {
      for (let y = -strokeWidth; y <= strokeWidth; y++) {
        if (x === 0 && y === 0) continue // 跳过中心点
        effects.push(`${x}px ${y}px 0 ${strokeColor}`)
      }
    }
  }

  // 添加阴影效果
  if (textShadow) {
    effects.push('2px 2px 4px rgba(0,0,0,0.5)')
  }

  return effects.length > 0 ? effects.join(', ') : 'none'
}

const currentTabLabel = computed(() => {
  const map: Record<string, string> = {
    model: t('llmSettings'),
    videoUnderstanding: t('videoUnderstandingSettings'),
    interface: t('interfaceSettings'),
    subtitle: t('subtitleSettings'),
    transcription: t('transcriptionSettings'),
    media: t('mediaCredentials'),
    tags: t('tagManagement'),
  }
  return map[props.activeTab] || props.activeTab
})

const colorPresets = ['#000000', '#ff0000', '#00ff00', '#0000ff', '#ffff00']

const fontWeights = computed(() => [
  { label: t('thin'), value: '300' },
  { label: t('normal'), value: '400' },
  { label: t('medium'), value: '500' },
  { label: t('semibold'), value: '600' },
  { label: t('bold'), value: '700' },
  { label: t('extrabold'), value: '800' },
])

const languageOptions = [
  { label: '中文', value: 'zh' },
  { label: 'English', value: 'en' },
]

const splitModel = computed({
  get() {
    switch (settings.selectedModelProvider) {
      case 'deepseek':
        return settings.deepseekModel
      case 'openai':
        return settings.openaiModel
      case 'qwen':
        return settings.qwenModel
      case 'ollama':
        return settings.ollamaModel || 'llama3'
      case 'local':
        return settings.localModel
      case 'moonshot':
        return settings.moonshotModel || 'moonshot-v1-8k'
      case 'volcano':
        return settings.volcanoModel || 'doubao-seed-2-0-lite-260428'
      case 'openrouter':
        return settings.openrouterModel || 'google/gemini-3-flash'
      case 'cerebras':
        return settings.cerebrasModel || 'llama3.1-8b'
      default:
        return ''
    }
  },
  set(val: string) {
    switch (settings.selectedModelProvider) {
      case 'deepseek':
        settings.deepseekModel = val
        break
      case 'openai':
        settings.openaiModel = val
        break
      case 'qwen':
        settings.qwenModel = val
        break
      case 'ollama':
        settings.ollamaModel = val
        break
      case 'local':
        settings.localModel = val
        break
      case 'moonshot':
        settings.moonshotModel = val
        break
      case 'volcano':
        settings.volcanoModel = val
        break
      case 'openrouter':
        settings.openrouterModel = val
        break
      case 'cerebras':
        settings.cerebrasModel = val
        break
    }
  },
})

const translateModel = computed({
  get() {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek':
        return settings.translateDeepseekModel
      case 'openai':
        return settings.translateOpenaiModel
      case 'qwen':
        return settings.translateQwenModel
      case 'ollama':
        return settings.translateOllamaModel || 'llama3'
      case 'local':
        return settings.translateLocalModel
      case 'moonshot':
        return settings.translateMoonshotModel || 'moonshot-v1-8k'
      case 'volcano':
        return settings.translateVolcanoModel || 'doubao-seed-2-0-lite-260428'
      case 'openrouter':
        return settings.translateOpenrouterModel || 'google/gemini-3-flash'
      case 'cerebras':
        return settings.translateCerebrasModel || 'llama3.1-8b'
      default:
        return ''
    }
  },
  set(val: string) {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek':
        settings.translateDeepseekModel = val
        break
      case 'openai':
        settings.translateOpenaiModel = val
        break
      case 'qwen':
        settings.translateQwenModel = val
        break
      case 'ollama':
        settings.translateOllamaModel = val
        break
      case 'local':
        settings.translateLocalModel = val
        break
      case 'moonshot':
        settings.translateMoonshotModel = val
        break
      case 'volcano':
        settings.translateVolcanoModel = val
        break
      case 'openrouter':
        settings.translateOpenrouterModel = val
        break
      case 'cerebras':
        settings.translateCerebrasModel = val
        break
    }
  },
})

const providerOptions = computed(() => [
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'OpenAI', value: 'openai' },
  { label: 'Qwen', value: 'qwen' },
  { label: 'Ollama', value: 'ollama' },
  { label: 'LM Studio', value: 'local' },
  { label: 'Moonshot', value: 'moonshot' },
  { label: t('volcano'), value: 'volcano' },
  { label: 'OpenRouter', value: 'openrouter' },
  { label: 'Cerebras', value: 'cerebras' },
])

const allTranscriptionEngines = computed(() => [
  { label: t('funasrNano'), value: 'funasr_gguf' },
  { label: 'GLM-ASR Stack (GLM-ASR-Nano + ForceAligner)', value: 'glm_asr' },
  { label: 'ElevenLabs Speech-to-Text', value: 'elevenlabs' },
])

const settings = reactive<FrontendSettings>({
  // Model settings
  selectedModelProvider: 'deepseek',
  // Translate LLM settings
  translateSelectedModelProvider: 'deepseek',
  // Proxy settings for different LLM operations
  splitUseProxy: false,
  splitNumThreads: 8,
  enableSplit: true,
  translateUseProxy: false,
  translateNumThreads: 8,
  enableTranslate: true,
  plainTranslate: false,
  // Provider-specific API keys and models (for split LLM)
  deepseekApiKey: 'sk-17047f89de904759a241f4086bd5a9bf',
  deepseekBaseUrl: 'https://api.deepseek.com',
  deepseekModel: 'deepseek-chat',
  openaiApiKey: '',
  openaiBaseUrl: 'https://api.chatanywhere.tech/v1',
  openaiModel: 'gpt-4o',
  qwenApiKey: '',
  qwenBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  qwenModel: 'qwen-plus',
  ollamaApiKey: '',
  ollamaBaseUrl: 'http://127.0.0.1:11434',
  ollamaModel: 'llama3',
  localApiKey: '',
  localBaseUrl: 'http://localhost:1234/v1',
  localModel: '',
  moonshotApiKey: '',
  moonshotBaseUrl: 'https://api.moonshot.cn/v1',
  moonshotModel: 'moonshot-v1-8k',
  volcanoApiKey: '',
  volcanoBaseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  volcanoModel: 'doubao-seed-2-0-lite-260428',
  openrouterApiKey: '',
  openrouterBaseUrl: 'https://openrouter.ai/api/v1',
  openrouterModel: 'google/gemini-3-flash',
  cerebrasApiKey: '',
  cerebrasBaseUrl: 'https://api.cerebras.ai/v1',
  cerebrasModel: 'llama3.1-8b',
  // Provider-specific API keys and models (for translate LLM)
  translateDeepseekApiKey: '',
  translateDeepseekBaseUrl: 'https://api.deepseek.com',
  translateDeepseekModel: 'deepseek-chat',
  translateOpenaiApiKey: '',
  translateOpenaiBaseUrl: 'https://api.chatanywhere.tech/v1',
  translateOpenaiModel: 'gpt-4o',
  translateQwenApiKey: '',
  translateQwenBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  translateQwenModel: 'qwen-plus',
  translateOllamaApiKey: '',
  translateOllamaBaseUrl: 'http://127.0.0.1:11434',
  translateOllamaModel: 'llama3',
  translateLocalApiKey: '',
  translateLocalBaseUrl: 'http://localhost:1234/v1',
  translateLocalModel: '',
  translateMoonshotApiKey: '',
  translateMoonshotBaseUrl: 'https://api.moonshot.cn/v1',
  translateMoonshotModel: 'moonshot-v1-8k',
  translateVolcanoApiKey: '',
  translateVolcanoBaseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  translateVolcanoModel: 'doubao-seed-2-0-lite-260428',
  translateOpenrouterApiKey: '',
  translateOpenrouterBaseUrl: 'https://openrouter.ai/api/v1',
  translateOpenrouterModel: 'google/gemini-3-flash',
  translateCerebrasApiKey: '',
  translateCerebrasBaseUrl: 'https://api.cerebras.ai/v1',
  translateCerebrasModel: 'llama3.1-8b',

  // Interface settings
  rawLanguage: 'zh',
  defaultTranslateLang: 'zh',
  hiddenCategories: [],
  // Raw Subtitle settings
  fontFamily: '宋体',
  previewText: t('defaultSubtitlePreviewText'),
  fontColor: '#ea9749',
  fontSize: 18,
  fontWeight: '400',
  backgroundColor: '#000000',
  borderRadius: 4,
  textShadow: false,
  textStroke: false,
  textStrokeColor: '#000000',
  textStrokeWidth: 2,
  backgroundStyle: 'semi-transparent',
  bottomDistance: 80,
  // Foreign Subtitle settings
  foreignFontFamily: 'Arial',
  foreignPreviewText: 'This is translated subtitle preview',
  foreignFontColor: '#ffffff',
  foreignFontSize: 16,
  foreignFontWeight: '400',
  foreignBackgroundColor: '#000000',
  foreignBorderRadius: 4,
  foreignTextShadow: false,
  foreignTextStroke: false,
  foreignTextStrokeColor: '#000000',
  foreignTextStrokeWidth: 2,
  foreignBackgroundStyle: 'semi-transparent',
  foreignBottomDistance: 120,
  // Media credentials
  bilibiliSessData: '',
  proxyUrl: '',
  downloadUseProxy: false,
  biliDownloadUseProxy: false,
  // Transcription Engine settings
  transcriptionPrimaryEngine: 'funasr_gguf',
  vadBackend: 'silero',
  fwsrModel: 'large-v3',
  useGpu: true, // GPU acceleration
  transcriptionElevenlabsApiKey: '',
  transcriptionElevenlabsModel: 'scribe_v1',
  transcriptionIncludePunctuation: true,
  hotwords: '',
  // Video Understanding settings
  vuThinkingBudget: 'low',
  vuCornerProvider: 'gemini',
  vuCornerGeminiApiKey: '',
  vuCornerGeminiBaseUrl: 'https://openrouter.ai/api/v1',
  vuCornerGeminiModel: 'google/gemini-2.5-flash',
  vuCornerGeminiOfficialApiKey: '',
  vuCornerGeminiOfficialBaseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
  vuCornerGeminiOfficialModel: 'gemini-2.5-flash',
  vuCornerMimoApiKey: '',
  vuCornerMimoBaseUrl: '',
  vuCornerMimoModel: 'mimo-v2.5',
  vuCornerOpenaiApiKey: '',
  vuCornerOpenaiBaseUrl: '',
  vuCornerOpenaiModel: '',
  vuSummaryProvider: 'deepseek',
  vuSummaryApiKey: '',
  vuSummaryBaseUrl: 'https://api.deepseek.com',
  vuSummaryModel: 'deepseek-chat',
  vuKnowledgeProvider: 'doubao',
  vuKnowledgeApiKey: '',
  vuKnowledgeBaseUrl: '',
  vuKnowledgeModel: '',
  vuCornerUseProxy: false,
  vuCornerCoverage: 0.6,
  vuSummaryUseProxy: false,
  vuKnowledgeUseProxy: false,
  vuDownloadUseProxy: false,
})

const loading = ref(false)
const saving = ref(false)

// yt-dlp 管理状态
const ytDlpStatus = ref<YtDlpStatus | null>(null)
const ytDlpLoading = ref(false)
const ytDlpInstalling = ref(false)
const ytDlpUpgrading = ref(false)

// YouTube cookies 状态
const cookiesStatus = ref<CookiesStatus | null>(null)
const cookiesLoading = ref(false)
const cookiesUploading = ref(false)
const cookiesHover = ref(false)
const bilibiliSessDataStatus = ref<BilibiliSessDataStatus | null>(null)
const bilibiliSessDataValidating = ref(false)

const VIDUNDER_MODELS: Array<Required<Pick<VidUnderModel, 'name' | 'label' | 'description' | 'totalSize'>>> = [
  {
    name: 'minicpm-v4.5',
    label: 'MiniCPM-V 4.5',
    description: 'Vision encoder + LLM decoder',
    totalSize: 6876000000,
  },
  {
    name: 'glm-ocr',
    label: 'GLM-OCR',
    description: 'OCR engine',
    totalSize: 1400000000,
  },
  {
    name: 'embedding',
    label: 'BGE Embedding (ONNX)',
    description: 'Text embedding (ONNX runtime, no torch)',
    totalSize: 95000000,
  },
  {
    name: 'fun-asr',
    label: 'FUN-ASR Nano',
    description: 'Fun-ASR speech recognition (ONNX + GGUF)',
    totalSize: 988000000,
  },
  {
    name: 'glm-asr',
    label: 'GLM-ASR Stack',
    description: 'GLM-ASR Nano + Qwen3 ForceAligner',
    totalSize: 6370000000,
  },
]

const vuSourceOptions = computed(() => [
  { label: t('vuHuggingFace'), value: 'hf' as VidUnderModelSource },
  { label: t('vuModelScope'), value: 'modelscope' as VidUnderModelSource },
])

const vuModels = ref<VidUnderModel[]>([])
const vuProgress = ref<VidUnderProgress>({})
const vuDownloadSources = reactive<Record<string, VidUnderModelSource>>({})
let vuPollTimer: ReturnType<typeof setInterval> | null = null

const normalizeVuStatus = (status?: string): VidUnderModelStatus => {
  if (
    status === 'downloaded' ||
    status === 'downloading' ||
    status === 'error' ||
    status === 'not_downloaded'
  ) {
    return status
  }
  return 'not_downloaded'
}

const resolveVuModelStatus = (model?: VidUnderModel): VidUnderModelStatus => {
  if (!model) return 'not_downloaded'
  if (model.status) return normalizeVuStatus(model.status)
  if (model.downloaded) return 'downloaded'
  if (model.downloading) return 'downloading'
  if (model.error) return 'error'
  return 'not_downloaded'
}

const mergeVuModels = (models: VidUnderModel[]): VidUnderModel[] => {
  const modelsByName = new Map(models.map((model) => [model.name, model]))
  const requiredModels = VIDUNDER_MODELS.map((definition) => {
    const remoteModel = modelsByName.get(definition.name)
    modelsByName.delete(definition.name)
    return {
      ...definition,
      ...remoteModel,
      label: remoteModel?.label || definition.label,
      description: remoteModel?.description || definition.description,
      totalSize: remoteModel?.totalSize ?? remoteModel?.total_size ?? definition.totalSize,
      total_size: remoteModel?.total_size ?? remoteModel?.totalSize ?? definition.totalSize,
      status: resolveVuModelStatus(remoteModel),
    }
  })

  return [...requiredModels, ...modelsByName.values()]
}

const ensureVuDownloadSources = () => {
  vuModels.value.forEach((model) => {
    if (!vuDownloadSources[model.name]) {
      vuDownloadSources[model.name] = 'hf'
    }
  })
}

const loadVuModels = async () => {
  try {
    vuModels.value = mergeVuModels(await loadVidUnderModels())
    ensureVuDownloadSources()
  } catch (e) {
    console.error('Failed to load vidUnder models:', e)
  }
}

const startVuDownload = async (modelName: string) => {
  try {
    const model = vuModels.value.find((item) => item.name === modelName)
    const source = vuDownloadSources[modelName] || 'hf'
    const useProxy = settings.vuDownloadUseProxy
    const proxy = useProxy ? settings.proxyUrl || undefined : undefined
    const force =
      (model ? getVuStatus(model) === 'downloaded' : false) ||
      vuProgress.value[modelName]?.force === true
    await downloadVidUnderModel(modelName, source, useProxy, proxy, force)
    const idx = vuModels.value.findIndex((model) => model.name === modelName)
    if (idx >= 0) vuModels.value[idx].status = 'downloading'
    startVuPolling()
  } catch (e: any) {
    const idx = vuModels.value.findIndex((model) => model.name === modelName)
    if (idx >= 0) vuModels.value[idx].status = 'error'
    ElMessage.error(e.message || t('vuDownloadError'))
  }
}

const pollVuProgress = async () => {
  vuProgress.value = await getVidUnderDownloadProgress()
  await loadVuModels()
  const anyDownloading = vuModels.value.some((model) => getVuStatus(model) === 'downloading')
  if (!anyDownloading) {
    stopVuPolling()
  }
}

const startVuPolling = () => {
  if (vuPollTimer) return
  void pollVuProgress().catch((error) => {
    console.error('Failed to poll vidUnder progress:', error)
  })
  vuPollTimer = setInterval(async () => {
    try {
      await pollVuProgress()
    } catch (error) {
      console.error('Failed to poll vidUnder progress:', error)
    }
  }, 2000)
}

const stopVuPolling = () => {
  if (vuPollTimer) {
    clearInterval(vuPollTimer)
    vuPollTimer = null
  }
}

const getVuModelTotalSize = (model: VidUnderModel): number => {
  const definition = VIDUNDER_MODELS.find((item) => item.name === model.name)
  return model.total_size ?? model.totalSize ?? definition?.totalSize ?? 0
}

const getVuDownloadedSize = (model: VidUnderModel): number => {
  const progress = vuProgress.value[model.name]
  return progress?.current ?? model.downloaded_size ?? 0
}

const getVuProgressPercent = (model: VidUnderModel): number => {
  const progress = vuProgress.value[model.name]
  const percent = progress?.percent ?? model.progress ?? 0
  return Math.min(100, Math.max(0, Math.round(percent)))
}

const getVuStatus = (model: VidUnderModel): VidUnderModelStatus => {
  const progressStatus = vuProgress.value[model.name]?.status
  if (
    progressStatus === 'downloaded' ||
    progressStatus === 'downloading' ||
    progressStatus === 'error' ||
    progressStatus === 'not_downloaded'
  ) {
    return progressStatus
  }
  return resolveVuModelStatus(model)
}

const getVuStatusText = (model: VidUnderModel): string => {
  const status = getVuStatus(model)
  if (status === 'downloaded') return t('vuDownloaded')
  if (status === 'downloading') return `${t('vuDownloading')} ${getVuProgressPercent(model)}%`
  if (status === 'error') return `${t('vuDownloadError')} - ${t('vuRetry')}`
  return t('vuNotDownloaded')
}

const getVuDownloadButtonText = (model: VidUnderModel): string => {
  const status = getVuStatus(model)
  if (status === 'error') return t('vuRetry')
  if (status === 'downloaded') return t('vuRedownload')
  return t('vuDownload')
}

const getVuStatusClass = (model: VidUnderModel): string => {
  const status = getVuStatus(model)
  if (status === 'downloaded') return 'text-green-600 dark:text-green-400'
  if (status === 'downloading') return 'text-teal-600 dark:text-teal-300'
  if (status === 'error') return 'text-red-500 dark:text-red-400'
  return 'text-slate-500 dark:text-gray-400'
}

// Computed properties for showing API key fields based on selected engine
const showElevenLabsSettings = computed(() => {
  return settings.transcriptionPrimaryEngine === 'elevenlabs'
})

const formatYtDlpComponentVersion = (version: string): string => {
  return version === '未安装' ? t('notInstalled') : version
}

// yt-dlp 管理函数
const loadYtDlpStatus = async () => {
  try {
    ytDlpLoading.value = true
    ytDlpStatus.value = await getYtDlpStatus()
  } catch (error) {
    console.error('Failed to load yt-dlp status:', error)
    ElMessage.error(t('ytDlpStatusLoadFailed'))
  } finally {
    ytDlpLoading.value = false
  }
}

// YouTube cookies 管理函数
const loadCookiesStatus = async () => {
  try {
    cookiesLoading.value = true
    cookiesStatus.value = await getYoutubeCookiesStatus()
  } catch (error) {
    console.error('Failed to load cookies status:', error)
  } finally {
    cookiesLoading.value = false
  }
}

const handleCookiesUpload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  const file = input.files[0]
  try {
    cookiesUploading.value = true
    const result = await uploadYoutubeCookies(file)
    if (result.success) {
      ElMessage.success(t('cookiesUploadSuccess'))
      await loadCookiesStatus()
    } else {
      ElMessage.error(result.error || t('uploadFailedMsg'))
    }
  } catch (error: any) {
    ElMessage.error(error.message || t('uploadFailedMsg'))
  } finally {
    cookiesUploading.value = false
    input.value = ''
  }
}

const formatCookiesTime = (isoTime: string): string => {
  const date = new Date(isoTime)
  return date.toLocaleString(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const formatBilibiliSessDataTime = (isoTime: string): string => {
  const date = new Date(isoTime)
  return date.toLocaleString(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const getBilibiliSessDataStatusText = (): string => {
  const status = bilibiliSessDataStatus.value
  const validation = status?.validation
  if (!status?.configured) return t('bilibiliSessDataNotConfigured')
  if (status.expired) return t('bilibiliSessDataExpired')
  if (validation?.valid) return t('bilibiliSessDataValid')
  if (validation?.checked) return t('bilibiliSessDataInvalid')
  return t('bilibiliSessDataConfigured')
}

const handleValidateBilibiliSessData = async () => {
  const sessdata = settings.bilibiliSessData.trim()
  if (!sessdata) {
    ElMessage.warning(t('bilibiliSessDataRequired'))
    return
  }

  try {
    bilibiliSessDataValidating.value = true
    bilibiliSessDataStatus.value = await validateBilibiliSessData(sessdata)
    const validation = bilibiliSessDataStatus.value.validation
    if (validation?.valid) {
      ElMessage.success(t('bilibiliSessDataValid'))
    } else {
      ElMessage.warning(validation?.message || t('bilibiliSessDataInvalid'))
    }
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : t('bilibiliSessDataValidateFailed')
    ElMessage.error(message)
  } finally {
    bilibiliSessDataValidating.value = false
  }
}

watch(
  () => settings.bilibiliSessData,
  () => {
    bilibiliSessDataStatus.value = null
  },
)

const handleInstallDeps = async () => {
  try {
    ytDlpInstalling.value = true
    const result = await installYtDlpDeps()
    if (result.success) {
      ElMessage.success(t('ytDlpDepsInstalledSuccess', { version: result.yt_dlp_version }))
      await loadYtDlpStatus()
    } else {
      ElMessage.error(t('installFailedWithDetail', { detail: result.detail }))
    }
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : t('installFailed')
    ElMessage.error(message)
  } finally {
    ytDlpInstalling.value = false
  }
}

const handleUpgrade = async () => {
  try {
    ytDlpUpgrading.value = true
    const result = await upgradeYtDlp()
    if (result.success) {
      if (result.upgraded) {
        ElMessage.success(
          t('upgradedToVersion', {
            currentVersion: result.current_version,
            newVersion: result.new_version,
          }),
        )
      } else {
        ElMessage.info(t('alreadyLatestVersion', { version: result.new_version }))
      }
      await loadYtDlpStatus()
    } else {
      ElMessage.error(t('upgradeFailedWithDetail', { detail: result.detail }))
    }
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : t('upgradeFailed')
    ElMessage.error(message)
  } finally {
    ytDlpUpgrading.value = false
  }
}

const loadSettings = async () => {
  try {
    loading.value = true

    // Load config settings and user hidden categories in parallel
    const [configData, userHiddenCategories] = await Promise.all([
      loadConfig(),
      loadUserHiddenCategories(),
    ])

    // Assign config data
    Object.assign(settings, configData)

    // Update hidden categories with user-defined ones
    settings.hiddenCategories = userHiddenCategories.usr_def_hidden_categories

    // Sync rawLanguage with localStorage lang setting
    const storedLang = localStorage.getItem('lang')
    if (storedLang && storedLang !== settings.rawLanguage) {
      settings.rawLanguage = storedLang
    }
  } catch (error) {
    console.error('Failed to load settings:', error)
    ElMessage.error(t('loadSettingsFailed'))
  } finally {
    loading.value = false
    // Mark settings as loaded so language watch only triggers on user changes
    nextTick(() => {
      settingsLoaded.value = true
    })
  }
}

// Tags management
const tags = ref<Tag[]>([])
const loadingTags = ref(false)
const creatingTag = ref(false)
const newTagName = ref('')
const newTagColor = ref(getRandomTagColor())
const selectedTagIds = ref<number[]>([])
const editingTagId = ref<number | null>(null)
const editingTagName = ref('')
const editingTagColor = ref(getRandomTagColor())
const tagColorPresets = TAG_COLOR_PRESETS

const getCurrentTagColors = () => tags.value.map((tag) => tag.color)
const pickSuggestedTagColor = () => getDistinctTagColor(getCurrentTagColors())

// Load tags
const loadTagsList = async () => {
  try {
    loadingTags.value = true
    tags.value = await loadTags()
    if (!newTagName.value.trim()) {
      newTagColor.value = pickSuggestedTagColor()
    }
  } catch (error) {
    console.error('Failed to load tags:', error)
    ElMessage.error(t('loadTagsFailed'))
  } finally {
    loadingTags.value = false
  }
}

// Create new tag
const createNewTag = async () => {
  if (!newTagName.value.trim()) {
    ElMessage.warning(t('pleaseEnterTagName'))
    return
  }
  try {
    creatingTag.value = true
    await createTag(newTagName.value.trim(), newTagColor.value)
    ElMessage.success(t('tagCreateSuccess'))
    newTagName.value = ''
    newTagColor.value = pickSuggestedTagColor()
    await loadTagsList()
  } catch (error: any) {
    ElMessage.error(error.message || t('tagCreateFailed'))
  } finally {
    creatingTag.value = false
  }
}

// Toggle tag selection for batch operations
const toggleTagSelection = (tagId: number) => {
  const index = selectedTagIds.value.indexOf(tagId)
  if (index > -1) {
    selectedTagIds.value.splice(index, 1)
  } else {
    selectedTagIds.value.push(tagId)
  }
}

// Start editing a tag
const startTagEdit = (tag: Tag) => {
  editingTagId.value = tag.id
  editingTagName.value = tag.name
  editingTagColor.value = tag.color
}

// Cancel tag editing
const cancelTagEdit = () => {
  editingTagId.value = null
  editingTagName.value = ''
  editingTagColor.value = pickSuggestedTagColor()
}

// Save tag edit
const saveTagEdit = async (tag: Tag) => {
  if (!editingTagName.value.trim()) {
    ElMessage.warning(t('tagNameRequired'))
    return
  }
  try {
    await updateTag(tag.id, editingTagName.value.trim(), editingTagColor.value)
    ElMessage.success(t('tagUpdateSuccess'))
    cancelTagEdit()
    await loadTagsList()
  } catch (error: any) {
    ElMessage.error(error.message || t('tagUpdateFailed'))
  }
}

// Delete single tag
const deleteSingleTag = async (tag: Tag) => {
  try {
    await ElMessageBox.confirm(
      t('deleteTagConfirmMessage', { name: tag.name }),
      t('confirmDeleteTitle'),
      {
        confirmButtonText: t('confirm'),
        cancelButtonText: t('cancel'),
        type: 'warning',
      },
    )
    await deleteTag(tag.id)
    ElMessage.success(t('tagDeleteSuccess'))
    await loadTagsList()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to delete tag:', error)
      ElMessage.error(error.message || t('tagDeleteFailed'))
    }
  }
}

// Batch delete tags
const batchDeleteTags = async () => {
  if (selectedTagIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      t('batchDeleteTagsConfirmMessage', { count: selectedTagIds.value.length }),
      t('confirmBatchDeleteTagsTitle'),
      {
        confirmButtonText: t('confirm'),
        cancelButtonText: t('cancel'),
        type: 'warning',
      },
    )
    const deletedCount = await batchDeleteTagsAPI(selectedTagIds.value)
    ElMessage.success(t('batchDeleteTagsSuccess', { count: deletedCount }))
    selectedTagIds.value = []
    await loadTagsList()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to batch delete tags:', error)
      ElMessage.error(error.message || t('batchDeleteTagsFailed'))
    }
  }
}

const saveSettings = async () => {
  try {
    saving.value = true

    // Save config settings and user hidden categories in parallel
    await Promise.all([saveConfig(settings), saveUserHiddenCategories(settings.hiddenCategories)])

    console.log('Settings saved successfully')
    ElMessage.success(t('settingsSaved'))

    // 同步原文字幕样式到全局状态
    updateSubtitleSettings({
      fontFamily: settings.fontFamily,
      fontColor: settings.fontColor,
      fontSize: settings.fontSize,
      fontWeight: settings.fontWeight,
      backgroundStyle: settings.backgroundStyle,
      backgroundColor: settings.backgroundColor,
      borderRadius: settings.borderRadius,
      textShadow: settings.textShadow,
      textStroke: settings.textStroke,
      textStrokeColor: settings.textStrokeColor,
      textStrokeWidth: settings.textStrokeWidth,
      bottomDistance: settings.bottomDistance,
    })

    // 同步外文字幕样式到全局状态
    updateForeignSubtitleSettings({
      fontFamily: settings.foreignFontFamily,
      fontColor: settings.foreignFontColor,
      fontSize: settings.foreignFontSize,
      fontWeight: settings.foreignFontWeight,
      backgroundStyle: settings.foreignBackgroundStyle,
      backgroundColor: settings.foreignBackgroundColor,
      borderRadius: settings.foreignBorderRadius,
      textShadow: settings.foreignTextShadow,
      textStroke: settings.foreignTextStroke,
      textStrokeColor: settings.foreignTextStrokeColor,
      textStrokeWidth: settings.foreignTextStrokeWidth,
      bottomDistance: settings.foreignBottomDistance,
    })

    emit('categories-updated') // 通知父组件更新分类过滤

    // Persist UI language and reload to apply new locale
    localStorage.setItem('lang', settings.rawLanguage)
    // Optional: reload if language changed? User might want to stay on settings.
  } catch (error) {
    console.error('Failed to save settings:', error)
    ElMessage.error(t('saveSettingsFailed'))
  } finally {
    saving.value = false
  }
}

// Track whether initial settings load is complete to avoid reload on load
const settingsLoaded = ref(false)

// Watch for language changes and reload to apply new locale
watch(
  () => settings.rawLanguage,
  (newLang, oldLang) => {
    if (settingsLoaded.value && newLang && newLang !== oldLang) {
      localStorage.setItem('lang', newLang)
      locale.value = newLang
      location.reload()
    }
  },
)

const resetSettings = () => {
  // Logic same as before...
  Object.assign(settings, {
    // Model settings
    selectedModelProvider: 'deepseek',
splitUseProxy: false,
  splitNumThreads: 8,
translateUseProxy: false,
  translateNumThreads: 8,
    plainTranslate: false,
    hotwords: '',
    // ... defaults ...
  })
}

const splitTesting = ref(false)
const translateTesting = ref(false)

const _runLLMTest = async (
  type: 'split' | 'translate',
  loadingRef: ReturnType<typeof ref<boolean>>,
) => {
    loadingRef.value = true
    try {
      await saveConfig(settings)
      ElMessage.success(t('settingsSavedStartTest'))
      await new Promise((resolve) => setTimeout(resolve, 500))
    const res = await fetch(`${BACKEND}/api/llm-test/?type=${type}`, { credentials: 'include' })
      const data = await res.json()
      if (data.success) {
      ElMessage.success(t('testSuccessWithResponse', { response: data.response }))
    } else {
      ElMessage.error(t('testFailedWithError', { error: data.error }))
    }
  } catch (err) {
    ElMessage.error(t('testFailedWithError', { error: err }))
  } finally {
    loadingRef.value = false
  }
}

const testSplitConnection = () => _runLLMTest('split', splitTesting)
const testTranslateConnection = () => _runLLMTest('translate', translateTesting)

const copyToClipboard = async (text: string) => {
  // ... existing copy logic ...
  try {
    if (navigator.clipboard && window.isSecureContext) {
      // Use Clipboard API if available and in secure context
      await navigator.clipboard.writeText(text)
      ElMessage.success(t('copiedToClipboard'))
    } else {
      // Fallback
      ElMessage.info(t('copyManually'))
    }
  } catch (e) {
    console.error(e)
  }
}

onMounted(() => {
  loadSettings()
  loadTagsList()
  loadYtDlpStatus()
  loadCookiesStatus()
  loadVuModels().then(() => {
    if (vuModels.value.some((model) => getVuStatus(model) === 'downloading')) {
      startVuPolling()
    }
  })
})

onUnmounted(() => {
  stopVuPolling()
})

// ===== API Token Management =====
const apiTokens = ref<Array<{ key: string; created_at: string }>>([])
const tokenLoading = ref(false)
const tokenCredsUsername = ref('')
const tokenCredsPassword = ref('')
const tokenCredsDialog = ref(false)
const tokenCredsMode = ref<'generate' | 'revoke'>('generate')
const tokenResultDialog = ref(false)
const tokenResultValue = ref('')

const fetchApiTokens = async () => {
  tokenLoading.value = true
  try {
    const res = await fetch(`${BACKEND}/api/auth/tokens/list`, { credentials: 'include' })
    const data = await res.json()
    if (data.success) {
      apiTokens.value = data.tokens
    }
  } catch {
    ElMessage.error(t('loadFailed'))
  } finally {
    tokenLoading.value = false
  }
}

const openGenerateDialog = () => {
  tokenCredsMode.value = 'generate'
  tokenCredsUsername.value = ''
  tokenCredsPassword.value = ''
  tokenCredsDialog.value = true
}

const openRevokeDialog = () => {
  tokenCredsMode.value = 'revoke'
  tokenCredsUsername.value = ''
  tokenCredsPassword.value = ''
  tokenCredsDialog.value = true
}

const submitTokenCreds = async () => {
  if (!tokenCredsUsername.value || !tokenCredsPassword.value) {
    ElMessage.warning(t('enterUsernamePassword'))
    return
  }

  try {
    if (tokenCredsMode.value === 'generate') {
      const res = await fetch(`${BACKEND}/api/auth/tokens/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: tokenCredsUsername.value, password: tokenCredsPassword.value }),
      })
      const data = await res.json()
      if (data.success) {
        tokenResultValue.value = data.token
        tokenResultDialog.value = true
        tokenCredsDialog.value = false
        fetchApiTokens()
      } else {
        ElMessage.error(data.error || t('operationFailed'))
      }
    } else {
      const res = await fetch(`${BACKEND}/api/auth/tokens/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: tokenCredsUsername.value,
          password: tokenCredsPassword.value,
        }),
      })
      const data = await res.json()
      if (data.success) {
        ElMessage.success(t('tokenRevoked'))
        tokenCredsDialog.value = false
        fetchApiTokens()
      } else {
        ElMessage.error(data.error || t('operationFailed'))
      }
    }
  } catch {
    ElMessage.error(t('networkError'))
  }
}

const copyToken = async () => {
  try {
    await navigator.clipboard.writeText(tokenResultValue.value)
    ElMessage.success(t('copiedToClipboard'))
  } catch {
    ElMessage.error(t('copyManually'))
  }
}

const closeTokenResult = () => {
  tokenResultDialog.value = false
  tokenResultValue.value = ''
}

watch(
  () => props.activeTab,
  (tab) => {
    if (tab === 'apiToken') {
      fetchApiTokens()
    }
  },
  { immediate: true },
)
</script>

<style scoped>
/* Custom styles for theme-aware settings controls */
input[type='range'] {
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  background: rgb(226 232 240);
  border-radius: 3px;
  outline: none;
}

:global(html.dark) input[type='range'] {
  background: rgb(55 65 81 / 0.7);
}

input[type='range']::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  background: rgb(20 184 166);
  border-radius: 50%;
  cursor: pointer;
}

input[type='range']::-moz-range-thumb {
  width: 18px;
  height: 18px;
  background: rgb(20 184 166);
  border: 0;
  border-radius: 50%;
  cursor: pointer;
}

:deep(.el-input__wrapper) {
  background-color: rgb(255 255 255);
  border: 1px solid rgb(203 213 225);
  box-shadow: none;
}

:global(html.dark) :deep(.el-input__wrapper) {
  background-color: rgb(31 41 55 / 0.7);
  border-color: rgb(255 255 255 / 0.1);
}

:deep(.el-input__wrapper.is-focus) {
  border-color: rgb(45 212 191 / 0.7);
  box-shadow: 0 0 0 2px rgb(20 184 166 / 0.2);
}

:deep(.el-input__inner) {
  color: rgb(15 23 42);
}

:global(html.dark) :deep(.el-input__inner) {
  color: rgb(243 244 246);
}

:deep(.el-input__inner::placeholder) {
  color: rgb(148 163 184);
}

:global(html.dark) :deep(.el-input__inner::placeholder) {
  color: rgb(107 114 128);
}

:deep(.el-input__password) {
  color: rgb(100 116 139);
}

:global(html.dark) :deep(.el-input__password) {
  color: rgb(156 163 175);
}

:deep(.el-switch__label) {
  color: rgb(100 116 139);
}

:global(html.dark) :deep(.el-switch__label) {
  color: rgb(156 163 175);
}

:deep(.el-switch__label.is-active) {
  color: rgb(13 148 136);
}

:global(html.dark) :deep(.el-switch__label.is-active) {
  color: rgb(45 212 191);
}

:deep(.el-switch.is-checked .el-switch__core) {
  background-color: rgb(20 184 166);
  border-color: rgb(20 184 166);
}

:deep(.el-checkbox__inner) {
  background-color: rgb(255 255 255);
  border-color: rgb(203 213 225);
}

:global(html.dark) :deep(.el-checkbox__inner) {
  background-color: rgb(31 41 55 / 0.7);
  border-color: rgb(75 85 99);
}

:deep(.el-checkbox__input.is-checked .el-checkbox__inner),
:deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner) {
  background-color: rgb(20 184 166);
  border-color: rgb(20 184 166);
}
</style>
