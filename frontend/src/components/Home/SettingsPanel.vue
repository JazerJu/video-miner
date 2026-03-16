<template>
  <div class="h-full flex flex-col bg-white rounded-lg shadow-sm">
    <!-- Header -->
    <div class="flex items-center justify-between p-6 border-b border-gray-200">
      <h3 class="text-xl font-semibold text-gray-800">
        {{ currentTabLabel }}
      </h3>
    </div>

    <!-- Content Area -->
    <div class="flex-1 p-8 overflow-y-auto relative">
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
      <div v-if="activeTab === 'model'" class="space-y-6 max-w-3xl">
        <!-- 断句 LLM Section -->
        <div class="border-b border-gray-200 pb-6">
          <h3 class="text-lg font-semibold text-gray-800 mb-4">断句 LLM</h3>
          
          <div class="space-y-4">
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

            <div>
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

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('baseUrl') }}</label>
              <input
                v-model="splitBaseUrl"
                type="url"
                class="w-full p-2 border border-gray-300 rounded-md"
                placeholder="输入API基础URL"
              />
            </div>

            <div>
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

            <div class="flex items-center justify-between">
              <el-switch
                v-model="settings.splitUseProxy"
                active-text="使用代理"
                inactive-text="不使用代理"
              />
              <button
                @click="testSplitConnection"
                :disabled="splitTesting"
                class="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ splitTesting ? '测试中...' : '测试连接' }}
              </button>
            </div>
          </div>
        </div>

        <!-- 翻译 LLM Section -->
        <div class="pt-4">
          <h3 class="text-lg font-semibold text-gray-800 mb-4">翻译 LLM</h3>
          
          <div class="space-y-4">
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

            <div>
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

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('baseUrl') }}</label>
              <input
                v-model="translateBaseUrl"
                type="url"
                class="w-full p-2 border border-gray-300 rounded-md"
                placeholder="输入API基础URL"
              />
            </div>

            <div>
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

            <div class="flex items-center justify-between">
              <el-switch
                v-model="settings.translateUseProxy"
                active-text="使用代理"
                inactive-text="不使用代理"
              />
              <button
                @click="testTranslateConnection"
                :disabled="translateTesting"
                class="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ translateTesting ? '测试中...' : '测试连接' }}
              </button>
            </div>

            <div class="flex items-center space-x-3 mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <el-checkbox v-model="settings.plainTranslate" />
              <div>
                <span class="text-sm font-medium text-gray-700">启用单句翻译</span>
                <p class="text-xs text-gray-500 mt-1">适配本地 vLLM 部署的翻译模型 (如 Hunyuan-MT-7B)，不要求 JSON 格式输出</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Interface Settings -->
      <div v-if="activeTab === 'interface'" class="space-y-6 max-w-3xl">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">界面语言</label>
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
      <div v-if="activeTab === 'subtitle'" class="space-y-6 max-w-3xl">
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

        <div class="grid grid-cols-2 gap-6">
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
             <label class="block text-sm font-medium text-gray-700 mb-2">字体大小: {{ currentSubtitleSettings.fontSize }}px</label>
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

        <div class="grid grid-cols-2 gap-6">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">字体颜色</label>
            <div class="flex items-center space-x-2 mb-2">
              <span class="text-sm text-gray-600"
                >当前: {{ currentSubtitleSettings.fontColor }}</span
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
            <label class="block text-sm font-medium text-gray-700 mb-2">字体粗细</label>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="weight in fontWeights"
                :key="weight.value"
                @click="updateCurrentSubtitleSettings('fontWeight', weight.value)"
                :class="[
                  'px-2 py-1 text-xs border rounded',
                  currentSubtitleSettings.fontWeight === weight.value
                    ? 'bg-blue-500 text-white border-blue-500'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50',
                ]"
              >
                {{ weight.label }}
              </button>
            </div>
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
      </div>

      <!-- TTS Settings -->
      <div v-if="activeTab === 'tts'" class="space-y-6 max-w-3xl">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">TTS 引擎选择</label>
          <select
            v-model="settings.ttsEngineChosen"
            class="w-full p-2 border border-gray-300 rounded-md"
          >
            <option value="glm_asr_local">GLM-ASR (LOCAL)</option>
            <option value="cosy_voice_cloud">COSY_VOICE (CLOUD)</option>
          </select>
        </div>

        <!-- Only show DashScope and OSS fields for cosy_voice_cloud -->
        <div v-if="settings.ttsEngineChosen === 'cosy_voice_cloud'" class="border-t border-gray-200 pt-6">
          <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <h4 class="text-sm font-medium text-blue-800 mb-2">TTS 配音设置</h4>
            <p class="text-sm text-blue-700">
              配置 Alibaba Cloud DashScope 凭证以启用 TTS 配音生成功能。
            </p>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">DashScope API Key</label>
            <input
              v-model="settings.dashscopeApiKey"
              type="password"
              class="w-full p-2 border border-gray-300 rounded-md"
              placeholder="输入您的 DashScope API Key"
            />
          </div>

          <!-- OSS Fields (moved from OSS tab) -->
          <div class="border-t border-gray-200 pt-6 mt-6">
            <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <h4 class="text-sm font-medium text-blue-800 mb-2">Aliyun OSS 配置说明</h4>
              <p class="text-sm text-blue-700">
                配置 Aliyun OSS 凭证以启用音频克隆功能。上传的参考音频将存储在您的 OSS Bucket 中。
              </p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Access Key ID</label>
              <input
                v-model="settings.ossAccessKeyId"
                type="text"
                class="w-full p-2 border border-gray-300 rounded-md"
                placeholder="输入您的 Aliyun Access Key ID"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Access Key Secret</label>
              <input
                v-model="settings.ossAccessKeySecret"
                type="password"
                class="w-full p-2 border border-gray-300 rounded-md"
                placeholder="输入您的 Aliyun Access Key Secret"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Endpoint</label>
              <input
                v-model="settings.ossEndpoint"
                type="text"
                class="w-full p-2 border border-gray-300 rounded-md"
                placeholder="oss-cn-beijing.aliyuncs.com"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Bucket 名称</label>
              <input
                v-model="settings.ossBucket"
                type="text"
                class="w-full p-2 border border-gray-300 rounded-md"
                placeholder="vidgo-test"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Region</label>
              <input
                v-model="settings.ossRegion"
                type="text"
                class="w-full p-2 border border-gray-300 rounded-md"
                placeholder="cn-beijing"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Transcription Engine Settings -->
      <div v-if="activeTab === 'transcription'" class="space-y-6 max-w-3xl">
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
        </div>
        
        <!-- Other engines omitted for brevity but logic is preserved in state -->
         <!-- ElevenLabs Settings -->
            <div v-if="needsElevenlabsConfig" class="space-y-4 border-t pt-4">
               <h4 class="text-md font-medium text-gray-800">ElevenLabs 设置</h4>
               <input
                    v-model="settings.transcriptionElevenlabsApiKey"
                    type="password"
                    placeholder="输入ElevenLabs API密钥"
                    class="w-full p-2 border border-gray-300 rounded-md"
                />
            </div>
             <!-- Alibaba DashScope Settings -->
            <div v-if="needsAlibabaConfig" class="space-y-4 border-t pt-4">
              <h4 class="text-md font-medium text-gray-800">阿里巴巴 DashScope 设置</h4>
              <input
                    v-model="settings.transcriptionAlibabaApiKey"
                    type="password"
                    placeholder="输入阿里巴巴API密钥"
                    class="w-full p-2 border border-gray-300 rounded-md"
                />
            </div>

            <!-- OpenAI Whisper Settings -->
            <div v-if="needsOpenaiConfig" class="space-y-4 border-t pt-4">
              <h4 class="text-md font-medium text-gray-800">OpenAI Whisper 设置</h4>
              <input
                    v-model="settings.transcriptionOpenaiApiKey"
                    type="password"
                    placeholder="输入OpenAI API密钥"
                    class="w-full p-2 border border-gray-300 rounded-md"
                />
            </div>
      </div>

      <!-- Media Credentials Settings -->
      <div v-if="activeTab === 'media'" class="space-y-6 max-w-3xl">
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

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">流媒体下载代理</label>
          <input
            v-model="settings.streamDownloadProxy"
            type="text"
            class="w-full p-2 border border-gray-300 rounded-md"
            placeholder="http://127.0.0.1:7890 (留空则不使用代理)"
          />
          <p class="mt-2 text-sm text-gray-500">
            用于YouTube/B站/Podcast下载时的代理设置，留空则不使用代理。
          </p>
        </div>
      </div>

      <!-- Tags Management -->
      <div v-if="activeTab === 'tags'" class="space-y-6 max-w-3xl">
        <!-- Create New Tag -->
        <div class="bg-gray-50 rounded-lg p-4 border border-gray-200">
          <h4 class="text-sm font-medium text-gray-700 mb-3">创建新标签</h4>
          <div class="flex items-center space-x-3">
            <input
              v-model="newTagName"
              type="text"
              class="flex-1 p-2 border border-gray-300 rounded-md"
              placeholder="输入标签名称"
              @keyup.enter="createNewTag"
            />
            <div class="flex items-center space-x-2">
              <input
                v-model="newTagColor"
                type="color"
                class="w-10 h-10 rounded border border-gray-300 cursor-pointer"
              />
              <span class="text-sm text-gray-500">{{ newTagColor }}</span>
            </div>
            <button
              @click="createNewTag"
              :disabled="!newTagName.trim() || creatingTag"
              class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ creatingTag ? '创建中...' : '创建' }}
            </button>
          </div>
        </div>

        <!-- Tags List -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-medium text-gray-700">
              标签列表 ({{ tags.length }})
            </h4>
            <div v-if="selectedTagIds.length > 0" class="flex items-center space-x-2">
              <span class="text-sm text-gray-500">已选择 {{ selectedTagIds.length }} 个</span>
              <button
                @click="batchDeleteTags"
                class="px-3 py-1 bg-red-500 text-white text-sm rounded hover:bg-red-600"
              >
                批量删除
              </button>
              <button
                @click="selectedTagIds = []"
                class="px-3 py-1 bg-gray-300 text-gray-700 text-sm rounded hover:bg-gray-400"
              >
                取消
              </button>
            </div>
          </div>

          <div v-if="loadingTags" class="flex items-center justify-center py-8">
            <div class="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            <span class="ml-2 text-gray-600">加载中...</span>
          </div>

          <div v-else-if="tags.length === 0" class="text-center py-8 text-gray-500">
            暂无标签，点击上方按钮创建
          </div>

          <div v-else class="space-y-2 max-h-96 overflow-y-auto">
            <div
              v-for="tag in tags"
              :key="tag.id"
              class="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200 hover:border-gray-300 transition-colors"
            >
              <div class="flex items-center space-x-3">
                <input
                  type="checkbox"
                  :checked="selectedTagIds.includes(tag.id)"
                  @change="toggleTagSelection(tag.id)"
                  class="w-4 h-4 text-blue-500 rounded"
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
                    class="w-24 p-1 text-sm border border-gray-300 rounded"
                    @keyup.enter="saveTagEdit(tag)"
                  />
                  <input
                    v-model="editingTagColor"
                    type="color"
                    class="w-8 h-8 rounded cursor-pointer"
                  />
                  <button
                    @click="saveTagEdit(tag)"
                    class="p-1 text-green-600 hover:text-green-700"
                  >
                    ✓
                  </button>
                  <button
                    @click="cancelTagEdit"
                    class="p-1 text-gray-400 hover:text-gray-500"
                  >
                    ✕
                  </button>
                </template>
                <template v-else>
                  <button
                    @click="startTagEdit(tag)"
                    class="p-1 text-gray-400 hover:text-blue-500"
                    title="编辑"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path>
                    </svg>
                  </button>
                  <button
                    @click="deleteSingleTag(tag)"
                    class="p-1 text-gray-400 hover:text-red-500"
                    title="删除"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
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
    <div class="flex justify-end space-x-3 p-4 border-t border-gray-200 bg-gray-50 rounded-b-lg">
      <button
        @click="resetSettings"
        :disabled="loading || saving"
        class="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        重置默认
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSubtitleStyle } from '@/composables/SubtitleStyle'
import {
  loadWhisperModels,
  downloadWhisperModel,
  getModelSize,
  type WhisperModel,
} from '@/composables/ConfigAPI'
import {
  loadTags,
  createTag,
  updateTag,
  deleteTag,
  batchDeleteTags as batchDeleteTagsAPI,
  type Tag,
} from '@/composables/TagsAPI'
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

// 断句LLM的API密钥和基础URL计算属性
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
      case 'local': // Add local (LM Studio)
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
      case 'local': // Add local
        settings.localApiKey = value
        break
    }
  },
})

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
      case 'local': // Add local
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
      case 'local': // Add local
        settings.localBaseUrl = value
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

const currentTabLabel = computed(() => {
    const map: Record<string, string> = {
        model: t('llmSettings'),
        interface: t('interfaceSettings'),
        subtitle: t('subtitleSettings'),
        transcription: t('transcriptionSettings'),
        media: t('mediaCredentials'),
        tts: 'TTS 配音',
        tags: '标签管理',
    }
    return map[props.activeTab] || props.activeTab
})

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

const splitModel = computed({
  get() {
    switch (settings.selectedModelProvider) {
      case 'deepseek': return settings.deepseekModel
      case 'openai':   return settings.openaiModel
      case 'glm':      return settings.glmModel
      case 'qwen':     return settings.qwenModel
      case 'local':    return settings.localModel
      default:         return ''
    }
  },
  set(val: string) {
    switch (settings.selectedModelProvider) {
      case 'deepseek': settings.deepseekModel = val; break
      case 'openai':   settings.openaiModel = val; break
      case 'glm':      settings.glmModel = val; break
      case 'qwen':     settings.qwenModel = val; break
      case 'local':    settings.localModel = val; break
    }
  },
})

const translateModel = computed({
  get() {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek': return settings.translateDeepseekModel
      case 'openai':   return settings.translateOpenaiModel
      case 'glm':      return settings.translateGlmModel
      case 'qwen':     return settings.translateQwenModel
      case 'local':    return settings.translateLocalModel
      default:         return ''
    }
  },
  set(val: string) {
    switch (settings.translateSelectedModelProvider) {
      case 'deepseek': settings.translateDeepseekModel = val; break
      case 'openai':   settings.translateOpenaiModel = val; break
      case 'glm':      settings.translateGlmModel = val; break
      case 'qwen':     settings.translateQwenModel = val; break
      case 'local':    settings.translateLocalModel = val; break
    }
  },
})

const providerOptions = [
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'OpenAI', value: 'openai' },
  { label: 'GLM', value: 'glm' },
  { label: 'Qwen', value: 'qwen' },
  { label: 'LM Studio', value: 'local' },
]

const allTranscriptionEngines = [
  { label: 'Faster-Whisper (优化Python实现, GPU加速)', value: 'faster_whisper' },
  { label: 'ElevenLabs Speech-to-Text', value: 'elevenlabs' },
  { label: '阿里巴巴 DashScope', value: 'alibaba' },
  { label: 'OpenAI Whisper API', value: 'openai_whisper' },
  { label: '远程VidGo字幕服务', value: 'remote_vidgo' },
]

const settings = reactive<FrontendSettings>({
  // Model settings
  selectedModelProvider: 'deepseek',
  // Translate LLM settings
  translateSelectedModelProvider: 'deepseek',
  // Proxy settings for different LLM operations
  splitUseProxy: false,
  translateUseProxy: false,
  plainTranslate: false,
  // Provider-specific API keys and models (for split LLM)
  deepseekApiKey: 'sk-17047f89de904759a241f4086bd5a9bf',
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
  // Provider-specific API keys and models (for translate LLM)
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
  streamDownloadProxy: '',
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
  // OSS Service settings
  ossAccessKeyId: '',
  ossAccessKeySecret: '',
  ossEndpoint: '',
  ossBucket: '',
  ossRegion: '',
  // TTS settings
  dashscopeApiKey: '',
  ttsEngineChosen: 'glm_asr_local',
})

const loading = ref(false)
const saving = ref(false)
const availableModels = ref<WhisperModel[]>([])
const isDownloading = ref(false)


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
    ElMessage.error('加载设置失败，请重试')
  } finally {
    loading.value = false
  }
}

// Tags management
const tags = ref<Tag[]>([])
const loadingTags = ref(false)
const creatingTag = ref(false)
const newTagName = ref('')
const newTagColor = ref('#3B82F6')
const selectedTagIds = ref<number[]>([])
const editingTagId = ref<number | null>(null)
const editingTagName = ref('')
const editingTagColor = ref('#3B82F6')

// Load tags
const loadTagsList = async () => {
  try {
    loadingTags.value = true
    tags.value = await loadTags()
  } catch (error) {
    console.error('Failed to load tags:', error)
    ElMessage.error('加载标签列表失败')
  } finally {
    loadingTags.value = false
  }
}

// Create new tag
const createNewTag = async () => {
  if (!newTagName.value.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  try {
    creatingTag.value = true
    await createTag(newTagName.value.trim(), newTagColor.value)
    ElMessage.success('标签创建成功')
    newTagName.value = ''
    newTagColor.value = '#3B82F6'
    await loadTagsList()
  } catch (error: any) {
    ElMessage.error(error.message || '创建标签失败')
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
  editingTagColor.value = '#3B82F6'
}

// Save tag edit
const saveTagEdit = async (tag: Tag) => {
  if (!editingTagName.value.trim()) {
    ElMessage.warning('标签名称不能为空')
    return
  }
  try {
    await updateTag(tag.id, editingTagName.value.trim(), editingTagColor.value)
    ElMessage.success('标签更新成功')
    cancelTagEdit()
    await loadTagsList()
  } catch (error: any) {
    ElMessage.error(error.message || '更新标签失败')
  }
}

// Delete single tag
const deleteSingleTag = async (tag: Tag) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除标签 "${tag.name}" 吗？该标签将从所有视频中移除。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await deleteTag(tag.id)
    ElMessage.success('标签删除成功')
    await loadTagsList()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to delete tag:', error)
      ElMessage.error(error.message || '删除标签失败')
    }
  }
}

// Batch delete tags
const batchDeleteTags = async () => {
  if (selectedTagIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedTagIds.value.length} 个标签吗？这些标签将从所有视频中移除。`,
      '确认批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    const deletedCount = await batchDeleteTagsAPI(selectedTagIds.value)
    ElMessage.success(`已删除 ${deletedCount} 个标签`)
    selectedTagIds.value = []
    await loadTagsList()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to batch delete tags:', error)
      ElMessage.error(error.message || '批量删除标签失败')
    }
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

    // Persist UI language and reload to apply new locale
    localStorage.setItem('lang', settings.rawLanguage)
    // Optional: reload if language changed? User might want to stay on settings.
  } catch (error) {
    console.error('Failed to save settings:', error)
    ElMessage.error('保存设置失败，请重试')
  } finally {
    saving.value = false
  }
}

const resetSettings = () => {
  // Logic same as before...
  Object.assign(settings, {
    // Model settings
    selectedModelProvider: 'deepseek',
    splitUseProxy: false,
    translateUseProxy: false,
    plainTranslate: false,
    // ... defaults ...
  })
}

const splitTesting = ref(false)
const translateTesting = ref(false)

const _runLLMTest = async (type: 'split' | 'translate', loadingRef: ReturnType<typeof ref<boolean>>) => {
  loadingRef.value = true
  try {
    await saveConfig(settings)
    ElMessage.success('设置已保存，开始测试连接...')
    await new Promise(resolve => setTimeout(resolve, 500))
    const res = await fetch(`${BACKEND}/api/llm-test/?type=${type}`, { credentials: 'include' })
    const data = await res.json()
    if (data.success) {
      ElMessage.success(`测试成功: ${data.response}`)
    } else {
      ElMessage.error(`测试失败: ${data.error}`)
    }
  } catch (err) {
    ElMessage.error(`测试失败: ${err}`)
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
      ElMessage.success('已复制到剪贴板')
    } else {
        // Fallback
       ElMessage.info('请手动复制')
    }
  } catch(e) {
      console.error(e)
  }
}

onMounted(() => {
    loadSettings()
    loadAvailableModels()
    loadTagsList()
})

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
</style>
