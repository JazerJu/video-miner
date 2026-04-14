<template>
  <div
    v-if="showSetting"
    class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    @click.self="showSetting = false"
  >
    <div class="bg-white rounded-lg shadow-xl w-[800px] h-[600px] flex overflow-hidden">
      <!-- Left Sidebar -->
      <div class="w-48 bg-gray-50 border-r border-gray-200">
        <div class="p-4">
          <h2 class="text-lg font-semibold text-gray-800 mb-4">{{ t('settingsTitle') }}</h2>
          <nav class="space-y-2">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              @click="activeTab = tab.id"
              :class="[
                'w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors',
                activeTab === tab.id ? 'bg-teal-600 text-white' : 'text-gray-700 hover:bg-gray-200',
              ]"
            >
              {{ tab.label }}
            </button>
          </nav>
        </div>
      </div>

      <!-- Main Content -->
      <div class="flex-1 flex flex-col">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-800">
            {{ tabs.find((t) => t.id === activeTab)?.label }}
          </h3>
          <button @click="closeDialog" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              ></path>
            </svg>
          </button>
        </div>

        <!-- Content Area -->
        <div class="flex-1 p-6 overflow-y-auto relative">
          <!-- Loading overlay -->
          <div
            v-if="loading"
            class="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-10"
          >
            <div class="flex items-center space-x-2">
              <div
                class="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"
              ></div>
              <span class="text-gray-600">{{ t('loadingSettings') }}</span>
            </div>
          </div>
          <!-- Model Settings -->
          <div v-if="activeTab === 'model'" class="space-y-6">
            <!-- 断句LLM Section -->
            <div class="border-t border-gray-200 pt-4">
              <h4 class="text-sm font-semibold text-gray-800 mb-3">断句 LLM</h4>
              
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">模型提供商选择</label>
                <select
                  v-model="settings.selectedModelProvider"
                  class="w-full p-2 border border-gray-300 rounded-md"
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

              <div class="mt-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('apiKey') }}</label>
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
                    class="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm text-gray-700 whitespace-nowrap"
                  >
                    {{ t('copy') }}
                  </button>
                </div>
              </div>

              <div class="mt-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('baseUrl') }}</label>
                <input
                  v-model="splitBaseUrl"
                  type="url"
                  class="w-full p-2 border border-gray-300 rounded-md"
                  placeholder="输入API基础URL"
                />
              </div>

              <div class="mt-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">
                  模型名称
                </label>
                <input
                  v-model="splitModel"
                  type="text"
                  class="w-full p-2 bg-gray-50 border border-gray-200 rounded-md text-gray-600"
                  placeholder="输入模型名称"
                />
              </div>

              <div class="mt-4 flex items-center justify-between">
                <el-switch
                  v-model="settings.splitUseProxy"
                  active-text="使用代理"
                  inactive-text="不使用代理"
                />
              </div>
            </div>

            <!-- 翻译LLM Section -->
            <div class="border-t border-gray-200 pt-4">
              <h4 class="text-sm font-semibold text-gray-800 mb-3">翻译 LLM</h4>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">模型提供商选择</label>
                <select
                  v-model="settings.translateSelectedModelProvider"
                  class="w-full p-2 border border-gray-300 rounded-md"
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

              <div class="mt-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('apiKey') }}</label>
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
                    class="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm text-gray-700 whitespace-nowrap"
                  >
                    {{ t('copy') }}
                  </button>
                </div>
              </div>

              <div class="mt-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('baseUrl') }}</label>
                <input
                  v-model="translateBaseUrl"
                  type="url"
                  class="w-full p-2 border border-gray-300 rounded-md"
                  placeholder="输入API基础URL"
                />
              </div>

              <div class="mt-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">
                  模型名称
                </label>
                <input
                  v-model="translateModel"
                  type="text"
                  class="w-full p-2 bg-gray-50 border border-gray-200 rounded-md text-gray-600"
                  placeholder="输入模型名称"
                />
              </div>

              <div class="mt-4 flex items-center justify-between">
                <el-switch
                  v-model="settings.translateUseProxy"
                  active-text="使用代理"
                  inactive-text="不使用代理"
                />
              </div>

              <div class="flex items-center space-x-3 mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <el-checkbox v-model="settings.plainTranslate" />
                <div>
                  <span class="text-sm font-medium text-gray-700">启用单句翻译</span>
                  <p class="text-xs text-gray-500 mt-1">适配本地 vLLM 部署的翻译模型 (如 Hunyuan-MT-7B)，不要求 JSON 格式输出</p>
                </div>
              </div>
            </div>

            <div class="flex justify-end">
              <button
                @click="testLLMConnection"
                :disabled="connectionTesting"
                class="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ connectionTesting ? '测试中...' : '测试连接' }}
              </button>
            </div>
          </div>

          <!-- Interface Settings -->
          <div v-if="activeTab === 'interface'" class="space-y-6">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">原始语言</label>
              <select
                v-model="settings.rawLanguage"
                class="w-full p-2 border border-gray-300 rounded-md"
              >
                <option v-for="lang in languageOptions" :key="lang.value" :value="lang.value">
                  {{ lang.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">默认译文语言</label>
              <p class="text-xs text-gray-500 mb-2">视频播放和字幕编辑中展示的译文字幕语言</p>
              <select
                v-model="settings.defaultTranslateLang"
                class="w-full p-2 border border-gray-300 rounded-md"
              >
                <option v-for="lang in languageOptions" :key="lang.value" :value="lang.value">
                  {{ lang.label }}
                </option>
              </select>
            </div>
          </div>

          <!-- Subtitle Settings -->
          <div v-if="activeTab === 'subtitle'" class="space-y-6">
            <!-- Subtitle Type Switch -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-3">字幕类型</label>
              <div class="flex bg-gray-100 rounded-lg p-1">
                <button
                  @click="subtitleType = 'raw'"
                  :class="[
                    'flex-1 py-2 px-4 text-sm font-medium rounded-md transition-colors',
                    subtitleType === 'raw'
                      ? 'bg-white text-blue-600 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700',
                  ]"
                >
                  原文字幕
                </button>
                <button
                  @click="subtitleType = 'foreign'"
                  :class="[
                    'flex-1 py-2 px-4 text-sm font-medium rounded-md transition-colors',
                    subtitleType === 'foreign'
                      ? 'bg-white text-blue-600 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700',
                  ]"
                >
                  译文字幕
                </button>
              </div>
              <p class="mt-2 text-sm text-gray-500">
                切换编辑{{ subtitleType === 'raw' ? '原文' : '外文' }}字幕的样式设置
              </p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">字体系列</label>
              <select
                :value="currentSubtitleSettings.fontFamily"
                @input="
                  updateCurrentSubtitleSettings(
                    'fontFamily',
                    ($event.target as HTMLSelectElement).value,
                  )
                "
                class="w-full p-2 border border-gray-300 rounded-md"
              >
                <option value="宋体">宋体</option>
                <option value="微软雅黑">微软雅黑</option>
                <option value="Arial">Arial</option>
                <option value="Times New Roman">Times New Roman</option>
                <option value="Helvetica">Helvetica</option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">预设文本</label>
              <input
                :value="currentSubtitleSettings.previewText"
                @input="
                  updateCurrentSubtitleSettings(
                    'previewText',
                    ($event.target as HTMLInputElement).value,
                  )
                "
                class="w-full p-2 border border-gray-300 rounded-md"
                placeholder="预设文本"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">字体颜色</label>
              <div class="flex items-center space-x-2 mb-2">
                <span class="text-sm text-gray-600"
                  >当前颜色: {{ currentSubtitleSettings.fontColor }}</span
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
                  class="w-8 h-8 rounded border"
                />
              </div>
              <div class="flex space-x-2">
                <button
                  v-for="color in colorPresets"
                  :key="color"
                  @click="updateCurrentSubtitleSettings('fontColor', color)"
                  :style="{ backgroundColor: color }"
                  class="w-6 h-6 rounded border-2 border-gray-300"
                ></button>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2"
                >字体大小: {{ currentSubtitleSettings.fontSize }}px</label
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
              <div class="flex justify-between text-xs text-gray-500 mt-1">
                <span>12px 小</span>
                <span>18px 中</span>
                <span>24px 中</span>
                <span>36px 大</span>
                <span>48px 特大</span>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">字体粗细</label>
              <div class="grid grid-cols-3 gap-2">
                <button
                  v-for="weight in fontWeights"
                  :key="weight.value"
                  @click="updateCurrentSubtitleSettings('fontWeight', weight.value)"
                  :class="[
                    'px-3 py-2 text-sm border rounded',
                    currentSubtitleSettings.fontWeight === weight.value
                      ? 'bg-blue-500 text-white border-blue-500'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50',
                  ]"
                >
                  {{ weight.label }}
                </button>
              </div>
            </div>
            <div>
              <div class="flex items-center justify-between mb-4">
                <span class="text-sm font-medium text-gray-700">显示设置</span>
              </div>

              <div class="space-y-4">
                <!-- 字幕背景样式选择 -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-2">字幕背景</label>
                  <select
                    v-model="backgroundStyleProxy"
                    class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="none">无背景</option>
                    <option value="semi-transparent">半透明背景</option>
                    <option value="solid">纯色背景</option>
                  </select>
                </div>

                <!-- 距底边距离设置 -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-2">距底边距离</label>
                  <div class="flex items-center space-x-3">
                    <input
                      type="range"
                      v-model="bottomDistanceProxy"
                      min="20"
                      max="200"
                      step="10"
                      class="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                    />
                    <span class="text-sm text-gray-500 min-w-[50px]"
                      >{{ bottomDistanceProxy }}px</span
                    >
                  </div>
                </div>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">背景色</label>
              <input
                type="color"
                :value="currentSubtitleSettings.backgroundColor"
                @input="
                  updateCurrentSubtitleSettings(
                    'backgroundColor',
                    ($event.target as HTMLInputElement).value,
                  )
                "
                class="w-12 h-8 rounded border"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2"
                >圆角: {{ currentSubtitleSettings.borderRadius }}px</label
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
                <span class="text-sm text-gray-700"
                  >文字阴影:
                  {{ currentSubtitleSettings.textShadow ? '启用阴影' : '禁用阴影' }}</span
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
                      currentSubtitleSettings.textShadow ? 'bg-blue-500' : 'bg-gray-300',
                    ]"
                  >
                    <div
                      :class="[
                        'w-5 h-5 bg-white rounded-full shadow transform transition-transform',
                        currentSubtitleSettings.textShadow ? 'translate-x-5' : 'translate-x-0',
                      ]"
                    ></div>
                  </div>
                </label>
              </div>

              <!-- Text Stroke Controls -->
              <div class="flex items-center justify-between">
                <span class="text-sm text-gray-700"
                  >文字描边:
                  {{ currentSubtitleSettings.textStroke ? '启用描边' : '禁用描边' }}</span
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
                      currentSubtitleSettings.textStroke ? 'bg-green-500' : 'bg-gray-300',
                    ]"
                  >
                    <div
                      :class="[
                        'w-5 h-5 bg-white rounded-full shadow transform transition-transform',
                        currentSubtitleSettings.textStroke ? 'translate-x-5' : 'translate-x-0',
                      ]"
                    ></div>
                  </div>
                </label>
              </div>

              <!-- Text Stroke Color -->
              <div v-if="currentSubtitleSettings.textStroke" class="space-y-2">
                <label class="block text-sm font-medium text-gray-700">描边颜色</label>
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
                    class="w-12 h-8 rounded cursor-pointer"
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
                    class="flex-1 px-3 py-1 border rounded text-sm"
                    placeholder="#000000"
                  />
                </div>
              </div>

              <!-- Text Stroke Width -->
              <div v-if="currentSubtitleSettings.textStroke" class="space-y-2">
                <label class="block text-sm font-medium text-gray-700"
                  >描边宽度: {{ currentSubtitleSettings.textStrokeWidth }}px</label
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
                <label class="block text-sm font-medium text-gray-700 mb-2">实时预览</label>
                <div
                  class="p-4 border-2 border-dashed border-gray-300 rounded-lg bg-gray-800 text-center"
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
              <p class="text-sm text-gray-500 text-center">
                预览效果将应用到{{ subtitleType === 'raw' ? '原文' : '外文' }}字幕显示
              </p>
            </div>

            <!-- Aspect Ratio Preview Buttons -->
            <div class="space-y-4">
              <label class="block text-sm font-medium text-gray-700">视频预览</label>
              <div class="flex space-x-4">
                <button
                  @click="showPreviewModal('16:9')"
                  class="flex-1 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
                >
                  16:9 横屏预览
                </button>
                <button
                  @click="showPreviewModal('3:4')"
                  class="flex-1 px-4 py-2 bg-green-500 text-white rounded-md hover:bg-green-600 transition-colors"
                >
                  3:4 竖屏预览
                </button>
              </div>
              <p class="text-sm text-gray-500 text-center">预览字幕在实际视频中的硬编码效果</p>
            </div>

            <!-- Preview Modal -->
            <div
              v-if="showPreview"
              class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60]"
              @click.self="closePreview"
            >
              <div class="bg-white rounded-lg p-6 max-w-4xl max-h-[90vh] overflow-auto">
                <div class="flex justify-between items-center mb-4">
                  <h3 class="text-lg font-semibold">{{ previewAspectRatio }} 字幕预览</h3>
                  <button @click="closePreview" class="text-gray-400 hover:text-gray-600">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M6 18L18 6M6 6l12 12"
                      ></path>
                    </svg>
                  </button>
                </div>

                <!-- Preview Container -->
                <div
                  class="relative bg-gray-800 mx-auto flex items-center justify-center"
                  :style="{
                    width: previewAspectRatio === '16:9' ? '640px' : '300px',
                    height: previewAspectRatio === '16:9' ? '360px' : '400px',
                  }"
                >
                  <!-- Background Text -->
                  <div class="text-gray-500 text-xl font-bold select-none">
                    {{ previewAspectRatio === '16:9' ? '1920*1080' : '1080*1440' }}
                  </div>

                  <!-- Raw Subtitle (原文字幕) -->
                  <div
                    class="absolute text-center px-2"
                    :style="{
                      bottom: settings.bottomDistance + 'px',
                      left: '50%',
                      transform: 'translateX(-50%)',
                      fontFamily: settings.fontFamily,
                      fontSize:
                        (previewAspectRatio === '16:9'
                          ? settings.fontSize
                          : settings.fontSize * 0.8) + 'px',
                      color: settings.fontColor,
                      fontWeight: settings.fontWeight,
                      backgroundColor:
                        settings.backgroundStyle === 'solid'
                          ? settings.backgroundColor
                          : settings.backgroundStyle === 'semi-transparent'
                            ? settings.backgroundColor + '80'
                            : 'transparent',
                      borderRadius: settings.borderRadius + 'px',
                      textShadow: settings.textShadow ? '2px 2px 4px rgba(0,0,0,0.5)' : 'none',
                      padding: settings.backgroundStyle !== 'none' ? '4px 8px' : '0',
                    }"
                  >
                    Example content Example content Example content
                  </div>

                  <!-- Foreign Subtitle (外文字幕) -->
                  <div
                    class="absolute text-center px-2"
                    :style="{
                      bottom: settings.foreignBottomDistance + 'px',
                      left: '50%',
                      transform: 'translateX(-50%)',
                      fontFamily: settings.foreignFontFamily,
                      fontSize:
                        (previewAspectRatio === '16:9'
                          ? settings.foreignFontSize
                          : settings.foreignFontSize * 0.8) + 'px',
                      color: settings.foreignFontColor,
                      fontWeight: settings.foreignFontWeight,
                      backgroundColor:
                        settings.foreignBackgroundStyle === 'solid'
                          ? settings.foreignBackgroundColor
                          : settings.foreignBackgroundStyle === 'semi-transparent'
                            ? settings.foreignBackgroundColor + '80'
                            : 'transparent',
                      borderRadius: settings.foreignBorderRadius + 'px',
                      textShadow: settings.foreignTextShadow
                        ? '2px 2px 4px rgba(0,0,0,0.5)'
                        : 'none',
                      padding: settings.foreignBackgroundStyle !== 'none' ? '4px 8px' : '0',
                    }"
                  >
                    这是一段示例文本
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Transcription Engine Settings -->
          <div v-if="activeTab === 'transcription'" class="space-y-6">
            <!-- Primary Engine Selection -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">转录引擎</label>
              <select
                v-model="settings.transcriptionPrimaryEngine"
                class="w-full p-2 border border-gray-300 rounded-md"
              >
                <option v-for="engine in allTranscriptionEngines" :key="engine.value" :value="engine.value">
                  {{ engine.label }}
                </option>
              </select>
            </div>

            <!-- Faster-Whisper Specific Settings -->
            <div v-if="settings.transcriptionPrimaryEngine === 'faster_whisper'" class="space-y-4 border-t pt-4">
              <h4 class="text-md font-medium text-gray-800">Faster-Whisper 设置</h4>

              <div class="p-3 bg-green-50 border border-green-200 rounded-md">
                <p class="text-sm text-green-700">
                  ✅ <strong>Faster-Whisper:</strong> 优化Python实现，GPU加速，字级时间戳，支持中英文
                </p>
              </div>

              <div class="flex items-center justify-between p-3 bg-gray-50 rounded-md border border-gray-200">
                <div>
                  <span class="text-sm font-medium text-gray-700">🚀 启用GPU加速</span>
                  <p class="text-xs text-gray-500 mt-1">
                    {{ settings.useGpu
                       ? 'CUDA GPU加速 (需要NVIDIA GPU)'
                       : 'CPU-only模式 (无需GPU，速度较慢)' }}
                  </p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" v-model="settings.useGpu" class="sr-only" />
                  <div
                    :class="[
                      'w-11 h-6 rounded-full transition-colors',
                      settings.useGpu ? 'bg-green-500' : 'bg-gray-300',
                    ]"
                  >
                    <div
                      :class="[
                        'w-5 h-5 bg-white rounded-full shadow transform transition-transform',
                        settings.useGpu ? 'translate-x-5' : 'translate-x-0',
                      ]"
                    ></div>
                  </div>
                </label>
              </div>


              <div class="flex justify-between items-center mb-2">
                <label class="block text-sm font-medium text-gray-700">模型</label>
                <button
                  @click="loadAvailableModels"
                  class="px-3 py-1 bg-blue-100 hover:bg-blue-200 text-blue-700 rounded text-sm"
                >
                  刷新模型列表
                </button>
              </div>
              <select
                v-model="settings.fwsrModel"
                class="w-full p-2 border border-gray-300 rounded-md"
              >
                <option v-for="model in availableModels" :key="model.name" :value="model.name">
                  {{ model.name }} ({{ model.size }})
                  {{ model.downloaded ? '✅' : model.downloading ? '⏳' : '⬇️' }}
                </option>
              </select>
              <p class="mt-2 text-sm text-gray-500">
                模型会自动下载到 models 目录
              </p>
             </div>

             <!-- ElevenLabs Settings -->
            <div v-if="needsElevenlabsConfig" class="space-y-4 border-t pt-4">
              <h4 class="text-md font-medium text-gray-800">ElevenLabs 设置</h4>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2"
                  >ElevenLabs API Key</label
                >
                <div class="flex items-center space-x-2">
                  <el-input
                    v-model="settings.transcriptionElevenlabsApiKey"
                    type="password"
                    show-password
                    placeholder="输入ElevenLabs API密钥"
                    class="flex-1"
                  />
                  <button
                    @click="copyToClipboard(settings.transcriptionElevenlabsApiKey)"
                    class="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm text-gray-700 whitespace-nowrap"
                  >
                    {{ t('copy') }}
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">模型</label>
                <select
                  v-model="settings.transcriptionElevenlabsModel"
                  class="w-full p-2 border border-gray-300 rounded-md"
                >
                  <option value="scribe_v1">Scribe v1</option>
                </select>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-sm text-gray-700">包含标点符号</span>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    v-model="settings.transcriptionIncludePunctuation"
                    class="sr-only"
                  />
                  <div
                    :class="[
                      'w-11 h-6 rounded-full transition-colors',
                      settings.transcriptionIncludePunctuation ? 'bg-blue-500' : 'bg-gray-300',
                    ]"
                  >
                    <div
                      :class="[
                        'w-5 h-5 bg-white rounded-full shadow transform transition-transform',
                        settings.transcriptionIncludePunctuation
                          ? 'translate-x-5'
                          : 'translate-x-0',
                      ]"
                    ></div>
                  </div>
                </label>
              </div>
            </div>

            <!-- Alibaba DashScope Settings -->
            <div v-if="needsAlibabaConfig" class="space-y-4 border-t pt-4">
              <h4 class="text-md font-medium text-gray-800">阿里巴巴 DashScope 设置</h4>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Alibaba API Key</label>
                <div class="flex items-center space-x-2">
                  <el-input
                    v-model="settings.transcriptionAlibabaApiKey"
                    type="password"
                    show-password
                    placeholder="输入阿里巴巴API密钥"
                    class="flex-1"
                  />
                  <button
                    @click="copyToClipboard(settings.transcriptionAlibabaApiKey)"
                    class="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm text-gray-700 whitespace-nowrap"
                  >
                    {{ t('copy') }}
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">模型</label>
                <select
                  v-model="settings.transcriptionAlibabaModel"
                  class="w-full p-2 border border-gray-300 rounded-md"
                >
                  <option value="paraformer-realtime-v2">Paraformer Realtime v2</option>
                </select>
              </div>
            </div>

            <!-- OpenAI Whisper Settings -->
            <div v-if="needsOpenaiConfig" class="space-y-4 border-t pt-4">
              <h4 class="text-md font-medium text-gray-800">OpenAI Whisper 设置</h4>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">OpenAI API Key</label>
                <div class="flex items-center space-x-2">
                  <el-input
                    v-model="settings.transcriptionOpenaiApiKey"
                    type="password"
                    show-password
                    placeholder="输入OpenAI API密钥"
                    class="flex-1"
                  />
                  <button
                    @click="copyToClipboard(settings.transcriptionOpenaiApiKey)"
                    class="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm text-gray-700 whitespace-nowrap"
                  >
                    {{ t('copy') }}
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">{{
                  t('baseUrl')
                }}</label>
                <input
                  v-model="settings.transcriptionOpenaiBaseUrl"
                  type="url"
                  class="w-full p-2 border border-gray-300 rounded-md"
                  placeholder="输入OpenAI Base URL"
                />
              </div>
            </div>

            <!-- Remote VidGo Service Settings -->
            <div
              v-if="needsRemoteVidGoConfig"
              class="space-y-4 border border-gray-200 rounded-lg p-4"
            >
              <h4 class="text-sm font-medium text-gray-800">远程VidGo字幕服务配置</h4>
              <p class="text-sm text-gray-600 mb-4">
                用户可在高性能主机中部署VidGo实例，并通过IP/域名链接，调用后端的字幕识别服务。
              </p>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2"
                  >服务器地址 (IP/域名)</label
                >
                <input
                  v-model="settings.remoteVidGoHost"
                  type="text"
                  class="w-full p-2 border border-gray-300 rounded-md"
                  placeholder="例: 192.168.1.100 或 vidgo.example.com"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">端口号</label>
                <input
                  v-model="settings.remoteVidGoPort"
                  type="number"
                  class="w-full p-2 border border-gray-300 rounded-md"
                  placeholder="8000"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">SSL设置</label>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" v-model="settings.remoteVidGoUseSsl" class="sr-only" />
                  <div
                    :class="[
                      'w-11 h-6 rounded-full transition-colors',
                      settings.remoteVidGoUseSsl ? 'bg-blue-500' : 'bg-gray-300',
                    ]"
                  >
                    <div
                      :class="[
                        'w-5 h-5 bg-white rounded-full shadow transform transition-transform',
                        settings.remoteVidGoUseSsl ? 'translate-x-5' : 'translate-x-0',
                      ]"
                    ></div>
                  </div>
                  <span class="ml-3 text-sm text-gray-700">启用SSL (HTTPS)</span>
                </label>
                <p class="mt-2 text-sm text-gray-500">
                  如果启用SSL并使用域名，则无需填写端口号（默认443）
                </p>
              </div>
            </div>

            <!-- Engine Info Section -->
            <div class="bg-blue-50 p-4 rounded-lg">
              <div class="flex items-start">
                <div class="flex-shrink-0">
                  <svg
                    class="h-5 w-5 text-blue-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    ></path>
                  </svg>
                </div>
                <div class="ml-3">
                  <h3 class="text-sm font-medium text-blue-800">转录引擎说明</h3>
                  <div class="mt-2 text-sm text-blue-700">
                    <ul class="space-y-1">
                      <li>
                        <strong>Whisper.cpp:</strong> 本地处理，无需API密钥，支持CPU/GPU加速，隐私性好
                      </li>
                      <li>
                        <strong>ElevenLabs:</strong> 高质量转录，支持多语言，需要API密钥，0.04元/分钟
                      </li>
                      <li>
                        <strong>阿里巴巴 DashScope:</strong> 中文效果佳，需要API密钥，0.012元/分钟
                      </li>
                      <li>
                        <strong>OpenAI Whisper:</strong> OpenAI官方API，高质量，需要API密钥，0.04元/分钟
                      </li>
                      <li>
                        <strong>远程VidGo字幕服务:</strong> 连接到远程VidGo实例，无需API密钥，需要配置服务器地址
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Media Credentials Settings -->
          <div v-if="activeTab === 'media'" class="space-y-6">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">B站登录SessData</label>
              <div class="flex items-center space-x-2">
                <el-input
                  v-model="settings.bilibiliSessData"
                  type="password"
                  show-password
                  placeholder="输入B站登录SessData"
                  class="flex-1"
                />
                <button
                  @click="copyToClipboard(settings.bilibiliSessData)"
                  class="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm text-gray-700 whitespace-nowrap"
                >
                  {{ t('copy') }}
                </button>
              </div>
              <p class="mt-2 text-sm text-gray-500">
                用于登录B站获取高清视频和字幕，请在浏览器中登录B站后获取SessData。
              </p>
            </div>

            <div class="border-t border-gray-200 pt-6 mt-6">
              <h4 class="text-sm font-medium text-gray-700 mb-4">网络代理设置</h4>
              <div>
                <label class="block text-sm font-medium text-gray-600 mb-2">代理服务器地址</label>
                <input
                  v-model="settings.proxyUrl"
                  type="text"
                  class="w-full p-2 border border-gray-300 rounded-md"
                  placeholder="http://host.docker.internal:7890 (留空则不使用代理)"
                />
                <p class="mt-2 text-sm text-gray-500">
                  统一代理地址，用于 yt-dlp 下载和 LLM 调用。Docker 部署时也可通过
                  <code class="bg-gray-100 px-1 rounded">HTTPS_PROXY</code>
                  环境变量配置。
                </p>
              </div>
              <div class="mt-4 space-y-3">
                <label class="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    v-model="settings.downloadUseProxy"
                    class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <span class="text-sm text-gray-700">流媒体下载走代理 (YouTube / Podcast)</span>
                </label>
                <label class="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    v-model="settings.splitUseProxy"
                    class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <span class="text-sm text-gray-700">字幕分割 (LLM) 走代理</span>
                </label>
                <label class="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    v-model="settings.translateUseProxy"
                    class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <span class="text-sm text-gray-700">字幕翻译 (LLM) 走代理</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex justify-end space-x-3 p-4 border-t border-gray-200">
          <button
            @click="resetSettings"
            :disabled="loading || saving"
            class="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            重置默认
          </button>
          <button
            @click="closeDialog"
            :disabled="saving"
            class="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            取消
          </button>
          <button
            @click="saveSettings"
            :disabled="loading || saving"
            class="px-4 py-2 text-sm text-white bg-blue-500 rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            <span
              v-if="saving"
              class="inline-block w-4 h-4 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin"
            ></span>
            {{ saving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import {
  loadConfig,
  saveConfig,
  loadUserHiddenCategories,
  saveUserHiddenCategories,
  type FrontendSettings,
  BACKEND,
} from '@/composables/ConfigAPI'
import { ElMessage } from '@/composables/useNotification'
import { useSubtitleStyle } from '@/composables/SubtitleStyle'
import {
  loadWhisperModels,
  downloadWhisperModel,
  getModelSize,
  type WhisperModel,
} from '@/composables/ConfigAPI'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  visible: boolean
  categories?: Array<{ id: number; name: string; items?: any[] }>
}>()

/** 2. declare the update event */
const emit = defineEmits<{
  /** called when we want to tell the parent to change `visible` */
  (e: 'update:visible', value: boolean): void
  /** called when hidden categories are updated */
  (e: 'categories-updated'): void
}>()

// 使用字幕样式composable
const { updateSubtitleSettings, updateForeignSubtitleSettings } = useSubtitleStyle()

// i18n functionality
const { t } = useI18n()

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

// 断句 LLM API Key - computed property
const splitApiKey = computed({
  get() {
    switch (settings.selectedModelProvider) {
      case 'deepseek':
        return settings.deepseekApiKey
      case 'openai':
        return settings.openaiApiKey
      case 'glm':
        return settings.glmApiKey
      case 'qwen':
        return settings.qwenApiKey
      case 'local':
        return settings.localApiKey || ''
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
      case 'glm':
        settings.glmApiKey = value
        break
      case 'qwen':
        settings.qwenApiKey = value
        break
      case 'local':
        settings.localApiKey = value
        break
    }
  },
})

// 断句 LLM Base URL - computed property
const splitBaseUrl = computed({
  get() {
    switch (settings.selectedModelProvider) {
      case 'deepseek':
        return settings.deepseekBaseUrl
      case 'openai':
        return settings.openaiBaseUrl
      case 'glm':
        return settings.glmBaseUrl
      case 'qwen':
        return settings.qwenBaseUrl
      case 'local':
        return settings.localBaseUrl || 'http://localhost:1234/v1'
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
      case 'glm':
        settings.glmBaseUrl = value
        break
      case 'qwen':
        settings.qwenBaseUrl = value
        break
      case 'local':
        settings.localBaseUrl = value
        break
    }
  },
})

// 翻译 LLM API Key - computed property
const translateApiKey = computed({
  get() {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek':
        return settings.translateDeepseekApiKey
      case 'openai':
        return settings.translateOpenaiApiKey
      case 'glm':
        return settings.translateGlmApiKey
      case 'qwen':
        return settings.translateQwenApiKey
      case 'local':
        return settings.translateLocalApiKey || ''
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
      case 'glm':
        settings.translateGlmApiKey = value
        break
      case 'qwen':
        settings.translateQwenApiKey = value
        break
      case 'local':
        settings.translateLocalApiKey = value
        break
    }
  },
})

// 翻译 LLM Base URL - computed property
const translateBaseUrl = computed({
  get() {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek':
        return settings.translateDeepseekBaseUrl
      case 'openai':
        return settings.translateOpenaiBaseUrl
      case 'glm':
        return settings.translateGlmBaseUrl
      case 'qwen':
        return settings.translateQwenBaseUrl
      case 'local':
        return settings.translateLocalBaseUrl || 'http://localhost:1234/v1'
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
      case 'glm':
        settings.translateGlmBaseUrl = value
        break
      case 'qwen':
        settings.translateQwenBaseUrl = value
        break
      case 'local':
        settings.translateLocalBaseUrl = value
        break
    }
  },
})

// Get current model for split LLM based on selected provider
const splitModel = computed(() => {
  switch (settings.selectedModelProvider) {
    case 'deepseek':
      return settings.deepseekModel
    case 'openai':
      return settings.openaiModel
    case 'glm':
      return settings.glmModel
    case 'qwen':
      return settings.qwenModel
    case 'local':
      return settings.localModel
    default:
      return ''
  }
})

// Get current model for translate LLM based on selected provider
const translateModel = computed(() => {
  switch (settings.translateSelectedModelProvider) {
    case 'deepseek':
      return settings.translateDeepseekModel
    case 'openai':
      return settings.translateOpenaiModel
    case 'glm':
      return settings.translateGlmModel
    case 'qwen':
      return settings.translateQwenModel
    case 'local':
      return settings.translateLocalModel
    default:
      return ''
  }
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
/** 3. a computed getter/setter that *maps* to the prop + emit */
const showSetting = computed<boolean>({
  get() {
    return props.visible
  },
  set(v: boolean) {
    emit('update:visible', v)
  },
})

const activeTab = ref('model')

const tabs = computed(() => [
  { id: 'model', label: t('llmSettings') },
  { id: 'interface', label: t('interfaceSettings') },
  { id: 'subtitle', label: t('subtitleSettings') },
  { id: 'transcription', label: t('transcriptionSettings') },
  { id: 'media', label: t('mediaCredentials') },
])

const colorPresets = ['#000000', '#ff0000', '#00ff00', '#0000ff', '#ffff00']

const fontWeights = [
  { label: '细体', value: '300' },
  { label: '正常', value: '400' },
  { label: '中等', value: '500' },
  { label: '半粗', value: '600' },
  { label: '粗体', value: '700' },
  { label: '特粗', value: '800' },
]

const languageOptions = [
  { label: '中文', value: 'zh' },
  { label: 'English', value: 'en' },
]

const providerOptions = [
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'OpenAI', value: 'openai' },
  { label: 'GLM', value: 'glm' },
  { label: 'Qwen', value: 'qwen' },
  { label: 'LMstudio', value: 'local' },
]

const allTranscriptionEngines = [
  { label: 'Faster-Whisper (优化Python实现, GPU加速)', value: 'faster_whisper' },
  { label: 'ElevenLabs Speech-to-Text', value: 'elevenlabs' },
  { label: '阿里巴巴 DashScope', value: 'alibaba' },
  { label: 'OpenAI Whisper API', value: 'openai_whisper' },
  { label: '远程VidGo字幕服务', value: 'remote_vidgo' },
]

const settings = reactive<FrontendSettings>({
  // Model settings (断句 LLM)
  selectedModelProvider: 'deepseek',
  splitUseProxy: false,
  // Provider-specific API keys and models (断句 LLM)
  deepseekApiKey: 'sk-17047f89de904759a241f4086bd5a9bf',
  deepseekBaseUrl: 'https://api.deepseek.com',
  deepseekModel: 'deepseek-chat',
  openaiApiKey: 'sk-qTbd1AR4oMuP71ziRngmk3i0djrWVfLtuisvYKCH5B9jLz9g',
  openaiBaseUrl: 'https://api.chatanywhere.tech/v1',
  openaiModel: 'gpt-4o',
  glmApiKey: 'sk-17047f89de904759a241f4086bd5a9bf',
  glmBaseUrl: 'https://api.deepseek.com',
  glmModel: 'glm-4',
  qwenApiKey: 'sk-944471ea4aef486ca2a82b2adf26c0cc',
  qwenBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  qwenModel: 'qwen-plus',
  localApiKey: '',
  localBaseUrl: 'http://localhost:1234/v1',
  localModel: '',
  // Translate LLM settings
  translateSelectedModelProvider: 'deepseek',
  translateUseProxy: false,
  plainTranslate: false,
  translateDeepseekApiKey: '',
  translateDeepseekBaseUrl: 'https://api.deepseek.com',
  translateDeepseekModel: 'deepseek-chat',
  translateOpenaiApiKey: '',
  translateOpenaiBaseUrl: 'https://api.chatanywhere.tech/v1',
  translateOpenaiModel: 'gpt-4o',
  translateGlmApiKey: '',
  translateGlmBaseUrl: 'https://open.bigmodel.cn/api/paas/v4',
  translateGlmModel: 'glm-4',
  translateQwenApiKey: '',
  translateQwenBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  translateQwenModel: 'qwen-plus',
  translateLocalApiKey: '',
  translateLocalBaseUrl: 'http://localhost:1234/v1',
  translateLocalModel: '',
  // Interface settings
  rawLanguage: 'zh',
  defaultTranslateLang: 'zh',
  hiddenCategories: [],
  // Raw Subtitle settings
  fontFamily: '宋体',
  previewText: '这是字幕预设文本',
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
  // Transcription Engine settings
  transcriptionPrimaryEngine: 'faster_whisper',
  fwsrModel: 'large-v3',
  useGpu: true,  // GPU acceleration
  transcriptionElevenlabsApiKey: '',
  transcriptionElevenlabsModel: 'scribe_v1',
  transcriptionIncludePunctuation: true,
  transcriptionAlibabaApiKey: '',
  transcriptionAlibabaModel: 'paraformer-realtime-v2',
  transcriptionOpenaiApiKey: '',
  transcriptionOpenaiBaseUrl: 'https://api.openai.com/v1',
  // Remote VidGo Service settings
  remoteVidGoHost: '',
  remoteVidGoPort: '8000',
  remoteVidGoUseSsl: false,
})

const loading = ref(false)
const saving = ref(false)
const availableModels = ref<WhisperModel[]>([])
const downloadProgress = ref(0)
const isDownloading = ref(false)
const isCheckingSize = ref(false)
const modelSizeInfo = ref('')
const showPreview = ref(false)
const previewAspectRatio = ref<'16:9' | '3:4'>('16:9')

// Computed properties for showing API key fields based on selected engine
const needsElevenlabsConfig = computed(() => {
  return settings.transcriptionPrimaryEngine === 'elevenlabs'
})

const needsAlibabaConfig = computed(() => {
  return settings.transcriptionPrimaryEngine === 'alibaba'
})

const needsOpenaiConfig = computed(() => {
  return settings.transcriptionPrimaryEngine === 'openai_whisper'
})

const needsRemoteVidGoConfig = computed(() => {
  return settings.transcriptionPrimaryEngine === 'remote_vidgo'
})

// Model management computed properties
const isCurrentModelDownloaded = computed(() => {
  const currentModel = availableModels.value.find((model) => model.name === settings.fwsrModel)
  return currentModel?.downloaded || false
})

const closeDialog = () => {
  showSetting.value = false
}

// Model management functions
const loadAvailableModels = async () => {
  try {
    const modelData = await loadWhisperModels()
    availableModels.value = modelData.models
  } catch (error) {
    console.error('Failed to load Whisper models:', error)
    ElMessage.error('加载模型列表失败')
  }
}

const checkModelSize = async (modelName: string) => {
  try {
    isCheckingSize.value = true
    const sizeData = await getModelSize(modelName)

    if (sizeData.exists) {
      ElMessage.success(
        `模型 ${modelName} 当前大小: ${sizeData.size_human} (${sizeData.file_count} 个文件)`,
      )
      modelSizeInfo.value = `${sizeData.size_human} (${sizeData.file_count} files)`
    } else {
      ElMessage.info(`模型 ${modelName} 文件夹不存在`)
      modelSizeInfo.value = '不存在'
    }
  } catch (error) {
    console.error('Failed to check model size:', error)
    ElMessage.error(`检查模型大小失败: ${error instanceof Error ? error.message : 'Unknown error'}`)
  } finally {
    isCheckingSize.value = false
  }
}

const downloadModel = async (modelName: string) => {
  try {
    isDownloading.value = true
    downloadProgress.value = 0

    await downloadWhisperModel(modelName, settings.transcriptionPrimaryEngine)
    ElMessage.success(`开始下载模型 ${modelName}`)

    // Simple polling without progress estimation
    const pollInterval = setInterval(async () => {
      try {
        const modelData = await loadWhisperModels()
        const model = modelData.models.find((m) => m.name === modelName)

        if (model?.downloaded) {
          clearInterval(pollInterval)
          isDownloading.value = false
          await loadAvailableModels() // Refresh the list
          ElMessage.success(`模型 ${modelName} 下载完成`)
        }
      } catch (error) {
        console.error('Error polling download status:', error)
      }
    }, 3000) // Poll every 3 seconds

    // Set a timeout to stop polling after 30 minutes
    setTimeout(
      () => {
        clearInterval(pollInterval)
        isDownloading.value = false
      },
      30 * 60 * 1000,
    )
  } catch (error) {
    console.error('Failed to download model:', error)
    ElMessage.error(`下载模型失败: ${error instanceof Error ? error.message : 'Unknown error'}`)
    isDownloading.value = false
  }
}

const showPreviewModal = (aspectRatio: '16:9' | '3:4') => {
  previewAspectRatio.value = aspectRatio
  showPreview.value = true
}

const closePreview = () => {
  showPreview.value = false
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

    console.log('Loaded user hidden categories:', userHiddenCategories)
  } catch (error) {
    console.error('Failed to load settings:', error)
    ElMessage.error('加载设置失败，请重试')
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  try {
    saving.value = true

    // Save config settings and user hidden categories in parallel
    await Promise.all([saveConfig(settings), saveUserHiddenCategories(settings.hiddenCategories)])

    console.log('Settings saved successfully')
    ElMessage.success('设置已保存')

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
    closeDialog()

    // Persist UI language and reload to apply new locale
    localStorage.setItem('lang', settings.rawLanguage)
    window.location.reload()
  } catch (error) {
    console.error('Failed to save settings:', error)
    ElMessage.error('保存设置失败，请重试')
  } finally {
    saving.value = false
  }
}

const resetSettings = () => {
  Object.assign(settings, {
    // Model settings (断句 LLM)
    selectedModelProvider: 'deepseek',
    splitUseProxy: false,
    // Provider-specific API keys and models (断句 LLM)
    deepseekApiKey: '',
    deepseekBaseUrl: 'https://api.deepseek.com',
    deepseekModel: 'deepseek-chat',
    openaiApiKey: '',
    openaiBaseUrl: 'https://api.chatanywhere.tech/v1',
    openaiModel: 'gpt-4o',
    glmApiKey: '',
    glmBaseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    glmModel: 'glm-4',
    qwenApiKey: '',
    qwenBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    qwenModel: 'qwen-plus',
    localApiKey: '',
    localBaseUrl: 'http://localhost:1234/v1',
    localModel: '',
    // Translate LLM settings
    translateSelectedModelProvider: 'deepseek',
    translateUseProxy: false,
    plainTranslate: false,
    translateDeepseekApiKey: '',
    translateDeepseekBaseUrl: 'https://api.deepseek.com',
    translateDeepseekModel: 'deepseek-chat',
    translateOpenaiApiKey: '',
    translateOpenaiBaseUrl: 'https://api.chatanywhere.tech/v1',
    translateOpenaiModel: 'gpt-4o',
    translateGlmApiKey: '',
    translateGlmBaseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    translateGlmModel: 'glm-4',
    translateQwenApiKey: '',
    translateQwenBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    translateQwenModel: 'qwen-plus',
    translateLocalApiKey: '',
    translateLocalBaseUrl: 'http://localhost:1234/v1',
    translateLocalModel: '',
    // Interface settings
    rawLanguage: 'zh',
    defaultTranslateLang: 'zh',
    // Raw Subtitle settings
    fontFamily: '宋体',
    previewText: '这是字幕预设文本',
    fontColor: '#ea9749',
    fontSize: 18,
    fontWeight: '400',
    backgroundColor: '#000000',
    borderRadius: 4,
    textShadow: false,
    textStroke: false,
    textStrokeColor: '#000000',
    textStrokeWidth: 2,
    backgroundStyle: 'semi-transparent' as 'none' | 'solid' | 'semi-transparent',
    bottomDistance: 80,
    // Foreign Subtitle settings
    foreignFontFamily: 'Arial',
    foreignPreviewText: 'This is foreign subtitle preview',
    foreignFontColor: '#ffffff',
    foreignFontSize: 16,
    foreignFontWeight: '400',
    foreignBackgroundColor: '#000000',
    foreignBorderRadius: 4,
    foreignTextShadow: false,
    foreignTextStroke: false,
    foreignTextStrokeColor: '#000000',
    foreignTextStrokeWidth: 2,
    foreignBackgroundStyle: 'semi-transparent' as 'none' | 'solid' | 'semi-transparent',
    foreignBottomDistance: 120,
    // Media credentials
    bilibiliSessData: '',
    proxyUrl: '',
    downloadUseProxy: false,
    // Transcription Engine settings
    transcriptionPrimaryEngine: 'faster_whisper',
    fwsrModel: 'large-v3',
    useGpu: true,  // GPU acceleration
    transcriptionElevenlabsApiKey: '',
    transcriptionElevenlabsModel: 'scribe_v1',
    transcriptionIncludePunctuation: true,
    transcriptionAlibabaApiKey: '',
    transcriptionAlibabaModel: 'paraformer-realtime-v2',
    transcriptionOpenaiApiKey: '',
    transcriptionOpenaiBaseUrl: 'https://api.openai.com/v1',
    // Remote VidGo Service settings
    remoteVidGoHost: '',
    remoteVidGoPort: '8000',
    remoteVidGoUseSsl: false,
  })
}

// Test LLM connection by sending a simple prompt
const connectionTesting = ref(false)
const testLLMConnection = async () => {
  connectionTesting.value = true
  try {
    // 先保存当前设置，确保后端能读取到最新的配置
    await saveConfig(settings)
    ElMessage.success('设置已保存，开始测试连接...')
    
    // 稍等片刻让后端加载新配置
    await new Promise(resolve => setTimeout(resolve, 500))
    
    const res = await fetch(`${BACKEND}/api/llm-test/`, { credentials: 'include' })
    const data = await res.json()
    if (data.success) {
      ElMessage.success(`测试成功: ${data.response}`)
    } else {
      ElMessage.error(`测试失败: ${data.error}`)
    }
  } catch (err) {
    ElMessage.error(`测试失败: ${err}`)
  } finally {
    connectionTesting.value = false
  }
}

const copyToClipboard = async (text: string) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      // Use Clipboard API if available and in secure context
      await navigator.clipboard.writeText(text)
      ElMessage.success('已复制到剪贴板')
    } else {
      // Fallback for older browsers or non-secure contexts
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.left = '-999999px'
      textArea.style.top = '-999999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()

      try {
        document.execCommand('copy')
        ElMessage.success('已复制到剪贴板')
      } catch (err) {
        console.error('Fallback copy failed: ', err)
        ElMessage.error('复制失败')
      } finally {
        textArea.remove()
      }
    }
  } catch (err) {
    console.error('Failed to copy: ', err)
    ElMessage.error('复制失败')
  }
}

// Load settings when dialog opens
watch(
  () => props.visible,
  (newVisible) => {
    if (newVisible) {
      loadSettings()
    }
  },
)

// 监听原文字幕样式变化，实时更新
watch(
  [
    () => settings.fontFamily,
    () => settings.fontColor,
    () => settings.fontSize,
    () => settings.fontWeight,
    () => settings.backgroundStyle,
    () => settings.backgroundColor,
    () => settings.borderRadius,
    () => settings.textShadow,
    () => settings.textStroke,
    () => settings.textStrokeColor,
    () => settings.textStrokeWidth,
    () => settings.bottomDistance,
  ],
  () => {
    // 实时同步原文字幕样式到全局状态，提供实时预览
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
  },
  { deep: true, immediate: false },
)

// 监听外文字幕样式变化，实时更新
watch(
  [
    () => settings.foreignFontFamily,
    () => settings.foreignFontColor,
    () => settings.foreignFontSize,
    () => settings.foreignFontWeight,
    () => settings.foreignBackgroundStyle,
    () => settings.foreignBackgroundColor,
    () => settings.foreignBorderRadius,
    () => settings.foreignTextShadow,
    () => settings.foreignTextStroke,
    () => settings.foreignTextStrokeColor,
    () => settings.foreignTextStrokeWidth,
    () => settings.foreignBottomDistance,
  ],
  () => {
    // 实时同步外文字幕样式到全局状态，提供实时预览
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
  },
  { deep: true, immediate: false },
)

// Load settings on component mount
onMounted(() => {
  if (props.visible) {
    loadSettings()
    loadAvailableModels()
  }
})

// Watch for dialog visibility to load models
watch(
  () => props.visible,
  (newVisible) => {
    if (newVisible) {
      loadSettings()
      loadAvailableModels()
    }
  },
)

// Watch for changes in rawLanguage setting and sync with localStorage
watch(
  () => settings.rawLanguage,
  (newLang) => {
    // Update localStorage and i18n locale when rawLanguage changes
    localStorage.setItem('lang', newLang)
    // Note: We could also update the i18n locale here if needed
    // but the page reload in LangToggle.vue handles this currently
  },
  { immediate: false },
)
</script>

<style scoped>
/* Custom styles for better appearance */
input[type='range'] {
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  outline: none;
}

input[type='range']::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  background: #3b82f6;
  border-radius: 50%;
  cursor: pointer;
}

input[type='range']::-moz-range-thumb {
  width: 18px;
  height: 18px;
  background: #3b82f6;
  border-radius: 50%;
  cursor: pointer;
  border: none;
}
</style>
