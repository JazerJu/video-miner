// 前端会编译后与后端运行在同一台主机，同一端口，所以生产中使用${window.location.port}
// export const BACKEND = `${window.location.protocol}//${window.location.hostname}:${window.location.port}`
// 开发中前后端端口不统一，使用默认的8000端口
export const BACKEND = `${window.location.protocol}//${window.location.hostname}:${import.meta.env.VITE_BACKEND_ORIGIN}`

import { getCSRFToken } from '@/composables/GetCSRFToken'

// User-defined hidden categories API functions
export async function loadUserHiddenCategories(): Promise<{
  hidden_categories: number[]
  usr_def_hidden_categories: number[]
  combined_hidden_categories: number[]
}> {
  try {
    const response = await fetch(`${BACKEND}/api/auth/user-hidden-categories/`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    })

    if (!response.ok) {
      // If user is not authenticated, fall back to localStorage
      if (response.status === 401) {
        return {
          hidden_categories: [],
          usr_def_hidden_categories: loadHiddenCategories(),
          combined_hidden_categories: loadHiddenCategories(),
        }
      }
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to load user hidden categories')
    }

    return {
      hidden_categories: result.hidden_categories || [],
      usr_def_hidden_categories: result.usr_def_hidden_categories || [],
      combined_hidden_categories: result.combined_hidden_categories || [],
    }
  } catch (error) {
    console.error('Error loading user hidden categories:', error)
    // Fallback to localStorage for unauthenticated users
    return {
      hidden_categories: [],
      usr_def_hidden_categories: loadHiddenCategories(),
      combined_hidden_categories: loadHiddenCategories(),
    }
  }
}

export async function saveUserHiddenCategories(hiddenCategories: number[]): Promise<void> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/auth/user-hidden-categories/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({
        usr_def_hidden_categories: hiddenCategories,
      }),
    })

    if (!response.ok) {
      // If user is not authenticated, fall back to localStorage
      if (response.status === 401) {
        saveHiddenCategories(hiddenCategories)
        return
      }
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to save user hidden categories')
    }
  } catch (error) {
    console.error('Error saving user hidden categories:', error)
    // Fallback to localStorage for unauthenticated users
    saveHiddenCategories(hiddenCategories)
    throw error
  }
}

// localStorage functions for hidden categories (fallback for unauthenticated users)
export function loadHiddenCategories(): number[] {
  try {
    const stored = localStorage.getItem('vidgo_hidden_categories')
    return stored ? JSON.parse(stored) : []
  } catch (error) {
    console.error('Error loading hidden categories:', error)
    return []
  }
}

export function saveHiddenCategories(hiddenCategories: number[]): void {
  try {
    localStorage.setItem('vidgo_hidden_categories', JSON.stringify(hiddenCategories))
  } catch (error) {
    console.error('Error saving hidden categories:', error)
  }
}

export interface ConfigData {
  DEFAULT: {
    selected_model_provider: string
    split_use_proxy: string
    deepseek_api_key: string
    deepseek_base_url: string
    deepseek_model: string
    openai_api_key: string
    openai_base_url: string
    openai_model: string
    glm_api_key: string
    glm_base_url: string
    glm_model: string
    qwen_api_key: string
    qwen_base_url: string
    qwen_model: string
    ollama_api_key: string
    ollama_base_url: string
    ollama_model: string
    local_api_key: string
    local_base_url: string
    local_model: string
    moonshot_api_key: string
    moonshot_base_url: string
    moonshot_model: string
    zhipu_api_key: string
    zhipu_base_url: string
    zhipu_model: string
    cerebras_api_key: string
    cerebras_base_url: string
    cerebras_model: string
    translate_selected_model_provider: string
    translate_deepseek_api_key: string
    translate_deepseek_base_url: string
    translate_deepseek_model: string
    translate_openai_api_key: string
    translate_openai_base_url: string
    translate_openai_model: string
    translate_glm_api_key: string
    translate_glm_base_url: string
    translate_glm_model: string
    translate_qwen_api_key: string
    translate_qwen_base_url: string
    translate_qwen_model: string
    translate_ollama_api_key: string
    translate_ollama_base_url: string
    translate_ollama_model: string
    translate_local_api_key: string
    translate_local_base_url: string
    translate_local_model: string
    translate_moonshot_api_key: string
    translate_moonshot_base_url: string
    translate_moonshot_model: string
    translate_zhipu_api_key: string
    translate_zhipu_base_url: string
    translate_zhipu_model: string
    translate_cerebras_api_key: string
    translate_cerebras_base_url: string
    translate_cerebras_model: string
    translate_use_proxy: string
    plain_translate: string
  }
  'Video watch': {
    raw_language: string
    default_translate_lang: string
  }
  'Subtitle settings': {
    font_family: string
    preview_text: string
    font_color: string
    font_size: string
    font_weight: string
    background_color: string
    border_radius: string
    text_shadow: string
    text_stroke: string
    text_stroke_color: string
    text_stroke_width: string
    background_style: string
    bottom_distance: string
  }
  'Foreign Subtitle settings': {
    foreign_font_family: string
    foreign_preview_text: string
    foreign_font_color: string
    foreign_font_size: string
    foreign_font_weight: string
    foreign_background_color: string
    foreign_border_radius: string
    foreign_text_shadow: string
    foreign_text_stroke: string
    foreign_text_stroke_color: string
    foreign_text_stroke_width: string
    foreign_background_style: string
    foreign_bottom_distance: string
  }
  'Media Credentials': {
    bilibili_sessdata: string
    proxy_url: string
    download_use_proxy: string
  }
  'Transcription Engine': {
    primary_engine: string
    fwsr_model: string
    use_gpu: string
    elevenlabs_api_key: string
    elevenlabs_model: string
    include_punctuation: string
    alibaba_api_key: string
    alibaba_model: string
    openai_api_key: string
    openai_base_url: string
  }
  'Remote VidGo Service': {
    host: string
    port: string
    use_ssl: string
  }
}

export interface FrontendSettings {
  // Split LLM settings
  selectedModelProvider: string
  splitUseProxy: boolean
  deepseekApiKey: string
  deepseekBaseUrl: string
  deepseekModel: string
  openaiApiKey: string
  openaiBaseUrl: string
  openaiModel: string
  glmApiKey: string
  glmBaseUrl: string
  glmModel: string
  qwenApiKey: string
  qwenBaseUrl: string
  qwenModel: string
  ollamaApiKey: string
  ollamaBaseUrl: string
  ollamaModel: string
  localApiKey: string
  localBaseUrl: string
  localModel: string
  moonshotApiKey: string
  moonshotBaseUrl: string
  moonshotModel: string
  zhipuApiKey: string
  zhipuBaseUrl: string
  zhipuModel: string
  cerebrasApiKey: string
  cerebrasBaseUrl: string
  cerebrasModel: string
  // Translate LLM settings
  translateSelectedModelProvider: string
  translateUseProxy: boolean
  plainTranslate: boolean
  translateDeepseekApiKey: string
  translateDeepseekBaseUrl: string
  translateDeepseekModel: string
  translateOpenaiApiKey: string
  translateOpenaiBaseUrl: string
  translateOpenaiModel: string
  translateGlmApiKey: string
  translateGlmBaseUrl: string
  translateGlmModel: string
  translateQwenApiKey: string
  translateQwenBaseUrl: string
  translateQwenModel: string
  translateOllamaApiKey: string
  translateOllamaBaseUrl: string
  translateOllamaModel: string
  translateLocalApiKey: string
  translateLocalBaseUrl: string
  translateLocalModel: string
  translateMoonshotApiKey: string
  translateMoonshotBaseUrl: string
  translateMoonshotModel: string
  translateZhipuApiKey: string
  translateZhipuBaseUrl: string
  translateZhipuModel: string
  translateCerebrasApiKey: string
  translateCerebrasBaseUrl: string
  translateCerebrasModel: string
  // Interface settings
  rawLanguage: string
  defaultTranslateLang: string
  hiddenCategories: number[]
  // Raw Subtitle settings
  fontFamily: string
  previewText: string
  fontColor: string
  fontSize: number
  fontWeight: string
  backgroundColor: string
  borderRadius: number
  textShadow: boolean
  textStroke: boolean
  textStrokeColor: string
  textStrokeWidth: number
  backgroundStyle: 'none' | 'solid' | 'semi-transparent'
  bottomDistance: number
  // Foreign Subtitle settings
  foreignFontFamily: string
  foreignPreviewText: string
  foreignFontColor: string
  foreignFontSize: number
  foreignFontWeight: string
  foreignBackgroundColor: string
  foreignBorderRadius: number
  foreignTextShadow: boolean
  foreignTextStroke: boolean
  foreignTextStrokeColor: string
  foreignTextStrokeWidth: number
  foreignBackgroundStyle: 'none' | 'solid' | 'semi-transparent'
  foreignBottomDistance: number
  bilibiliSessData: string
  proxyUrl: string
  downloadUseProxy: boolean
  // Transcription Engine settings
  transcriptionPrimaryEngine: string
  fwsrModel: string
  useGpu: boolean  // GPU acceleration toggle
  transcriptionElevenlabsApiKey: string
  transcriptionElevenlabsModel: string
  transcriptionIncludePunctuation: boolean
  transcriptionAlibabaApiKey: string
  transcriptionAlibabaModel: string
  transcriptionOpenaiApiKey: string
  transcriptionOpenaiBaseUrl: string
  // Remote VidGo Service settings
  remoteVidGoHost: string
  remoteVidGoPort: string
  remoteVidGoUseSsl: boolean
}

export async function loadConfig(): Promise<FrontendSettings> {
  try {
    const response = await fetch(`${BACKEND}/api/config/`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to load config')
    }

    const data = result.data as ConfigData

    // Convert backend format to frontend format
    return {
      selectedModelProvider: data.DEFAULT?.selected_model_provider || 'deepseek',
      deepseekApiKey: data.DEFAULT?.deepseek_api_key || '',
      deepseekBaseUrl: data.DEFAULT?.deepseek_base_url || 'https://api.deepseek.com',
      deepseekModel: data.DEFAULT?.deepseek_model || 'deepseek-chat',
      openaiApiKey: data.DEFAULT?.openai_api_key || '',
      openaiBaseUrl: data.DEFAULT?.openai_base_url || 'https://api.chatanywhere.tech/v1',
      openaiModel: data.DEFAULT?.openai_model || 'gpt-4o',
      glmApiKey: data.DEFAULT?.glm_api_key || '',
      glmBaseUrl: data.DEFAULT?.glm_base_url || 'https://open.bigmodel.cn/api/paas/v4',
      glmModel: data.DEFAULT?.glm_model || 'glm-4',
      qwenApiKey: data.DEFAULT?.qwen_api_key || '',
      qwenBaseUrl:
        data.DEFAULT?.qwen_base_url || 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      qwenModel: data.DEFAULT?.qwen_model || 'qwen-plus',
      ollamaApiKey: data.DEFAULT?.ollama_api_key || '',
      ollamaBaseUrl: data.DEFAULT?.ollama_base_url || 'http://127.0.0.1:11434',
      ollamaModel: data.DEFAULT?.ollama_model || 'llama3',
      localApiKey: data.DEFAULT?.local_api_key || '',
      localBaseUrl: data.DEFAULT?.local_base_url || 'http://localhost:1234/v1',
      localModel: data.DEFAULT?.local_model || '',
      moonshotApiKey: data.DEFAULT?.moonshot_api_key || '',
      moonshotBaseUrl: data.DEFAULT?.moonshot_base_url || 'https://api.moonshot.cn/v1',
      moonshotModel: data.DEFAULT?.moonshot_model || 'moonshot-v1-8k',
      zhipuApiKey: data.DEFAULT?.zhipu_api_key || '',
      zhipuBaseUrl: data.DEFAULT?.zhipu_base_url || 'https://open.bigmodel.cn/api/paas/v4',
      zhipuModel: data.DEFAULT?.zhipu_model || 'glm-4-plus',
      cerebrasApiKey: data.DEFAULT?.cerebras_api_key || '',
      cerebrasBaseUrl: data.DEFAULT?.cerebras_base_url || 'https://api.cerebras.ai/v1',
      cerebrasModel: data.DEFAULT?.cerebras_model || 'llama3.1-8b',
      splitUseProxy: data.DEFAULT?.split_use_proxy === 'true',
      translateSelectedModelProvider:
        data.DEFAULT?.translate_selected_model_provider || 'deepseek',
      translateDeepseekApiKey: data.DEFAULT?.translate_deepseek_api_key || '',
      translateDeepseekBaseUrl:
        data.DEFAULT?.translate_deepseek_base_url || 'https://api.deepseek.com',
      translateDeepseekModel: data.DEFAULT?.translate_deepseek_model || 'deepseek-chat',
      translateOpenaiApiKey: data.DEFAULT?.translate_openai_api_key || '',
      translateOpenaiBaseUrl:
        data.DEFAULT?.translate_openai_base_url || 'https://api.chatanywhere.tech/v1',
      translateOpenaiModel: data.DEFAULT?.translate_openai_model || 'gpt-4o',
      translateGlmApiKey: data.DEFAULT?.translate_glm_api_key || '',
      translateGlmBaseUrl:
        data.DEFAULT?.translate_glm_base_url || 'https://open.bigmodel.cn/api/paas/v4',
      translateGlmModel: data.DEFAULT?.translate_glm_model || 'glm-4',
      translateQwenApiKey: data.DEFAULT?.translate_qwen_api_key || '',
      translateQwenBaseUrl:
        data.DEFAULT?.translate_qwen_base_url ||
        'https://dashscope.aliyuncs.com/compatible-mode/v1',
      translateQwenModel: data.DEFAULT?.translate_qwen_model || 'qwen-plus',
      translateOllamaApiKey: data.DEFAULT?.translate_ollama_api_key || '',
      translateOllamaBaseUrl: data.DEFAULT?.translate_ollama_base_url || 'http://127.0.0.1:11434',
      translateOllamaModel: data.DEFAULT?.translate_ollama_model || 'llama3',
      translateLocalApiKey: data.DEFAULT?.translate_local_api_key || '',
      translateLocalBaseUrl:
        data.DEFAULT?.translate_local_base_url || 'http://localhost:1234/v1',
      translateLocalModel: data.DEFAULT?.translate_local_model || '',
      translateMoonshotApiKey: data.DEFAULT?.translate_moonshot_api_key || '',
      translateMoonshotBaseUrl: data.DEFAULT?.translate_moonshot_base_url || 'https://api.moonshot.cn/v1',
      translateMoonshotModel: data.DEFAULT?.translate_moonshot_model || 'moonshot-v1-8k',
      translateZhipuApiKey: data.DEFAULT?.translate_zhipu_api_key || '',
      translateZhipuBaseUrl: data.DEFAULT?.translate_zhipu_base_url || 'https://open.bigmodel.cn/api/paas/v4',
      translateZhipuModel: data.DEFAULT?.translate_zhipu_model || 'glm-4-plus',
      translateCerebrasApiKey: data.DEFAULT?.translate_cerebras_api_key || '',
      translateCerebrasBaseUrl: data.DEFAULT?.translate_cerebras_base_url || 'https://api.cerebras.ai/v1',
      translateCerebrasModel: data.DEFAULT?.translate_cerebras_model || 'llama3.1-8b',
      translateUseProxy: data.DEFAULT?.translate_use_proxy === 'true',
      plainTranslate: data.DEFAULT?.plain_translate === 'true',
      // Interface settings
      rawLanguage: data['Video watch']?.raw_language || 'zh',
      defaultTranslateLang: data['Video watch']?.default_translate_lang || 'zh',
      hiddenCategories: [], // Will be loaded separately via loadUserHiddenCategories
      // Raw Subtitle settings
      fontFamily: data['Subtitle settings']?.font_family || '宋体',
      previewText: data['Subtitle settings']?.preview_text || '这是字幕预设文本',
      fontColor: data['Subtitle settings']?.font_color || '#ea9749',
      fontSize: parseInt(data['Subtitle settings']?.font_size || '18'),
      fontWeight: data['Subtitle settings']?.font_weight || '400',
      backgroundColor: data['Subtitle settings']?.background_color || '#000000',
      borderRadius: parseInt(data['Subtitle settings']?.border_radius || '4'),
      textShadow: data['Subtitle settings']?.text_shadow === 'true',
      textStroke: data['Subtitle settings']?.text_stroke === 'true',
      textStrokeColor: data['Subtitle settings']?.text_stroke_color || '#000000',
      textStrokeWidth: parseInt(data['Subtitle settings']?.text_stroke_width || '2'),
      backgroundStyle:
        (data['Subtitle settings']?.background_style as 'none' | 'solid' | 'semi-transparent') ||
        'semi-transparent',
      bottomDistance: parseInt(data['Subtitle settings']?.bottom_distance || '80'),
      // Foreign Subtitle settings
      foreignFontFamily: data['Foreign Subtitle settings']?.foreign_font_family || 'Arial',
      foreignPreviewText:
        data['Foreign Subtitle settings']?.foreign_preview_text ||
        'This is foreign subtitle preview',
      foreignFontColor: data['Foreign Subtitle settings']?.foreign_font_color || '#ffffff',
      foreignFontSize: parseInt(data['Foreign Subtitle settings']?.foreign_font_size || '16'),
      foreignFontWeight: data['Foreign Subtitle settings']?.foreign_font_weight || '400',
      foreignBackgroundColor:
        data['Foreign Subtitle settings']?.foreign_background_color || '#000000',
      foreignBorderRadius: parseInt(
        data['Foreign Subtitle settings']?.foreign_border_radius || '4',
      ),
      foreignTextShadow: data['Foreign Subtitle settings']?.foreign_text_shadow === 'true',
      foreignTextStroke: data['Foreign Subtitle settings']?.foreign_text_stroke === 'true',
      foreignTextStrokeColor:
        data['Foreign Subtitle settings']?.foreign_text_stroke_color || '#000000',
      foreignTextStrokeWidth: parseInt(
        data['Foreign Subtitle settings']?.foreign_text_stroke_width || '2',
      ),
      foreignBackgroundStyle:
        (data['Foreign Subtitle settings']?.foreign_background_style as
          | 'none'
          | 'solid'
          | 'semi-transparent') || 'semi-transparent',
      foreignBottomDistance: parseInt(
        data['Foreign Subtitle settings']?.foreign_bottom_distance || '120',
      ),
      bilibiliSessData: data['Media Credentials']?.bilibili_sessdata || '',
      proxyUrl: data['Media Credentials']?.proxy_url || '',
      downloadUseProxy: data['Media Credentials']?.download_use_proxy === 'true',
      // Transcription Engine settings
      transcriptionPrimaryEngine: data['Transcription Engine']?.primary_engine || 'faster_whisper',
      fwsrModel: data['Transcription Engine']?.fwsr_model || 'large-v3',
      useGpu: data['Transcription Engine']?.use_gpu === 'true',
      transcriptionElevenlabsApiKey: data['Transcription Engine']?.elevenlabs_api_key || '',
      transcriptionElevenlabsModel: data['Transcription Engine']?.elevenlabs_model || 'scribe_v1',
      transcriptionIncludePunctuation: data['Transcription Engine']?.include_punctuation === 'true',
      transcriptionAlibabaApiKey: data['Transcription Engine']?.alibaba_api_key || '',
      transcriptionAlibabaModel:
        data['Transcription Engine']?.alibaba_model || 'paraformer-realtime-v2',
      transcriptionOpenaiApiKey: data['Transcription Engine']?.openai_api_key || '',
      transcriptionOpenaiBaseUrl:
        data['Transcription Engine']?.openai_base_url || 'https://api.openai.com/v1',
      // Remote VidGo Service settings
      remoteVidGoHost: data['Remote VidGo Service']?.host || '',
      remoteVidGoPort: data['Remote VidGo Service']?.port || '8000',
      remoteVidGoUseSsl: data['Remote VidGo Service']?.use_ssl === 'true',
    }
  } catch (error) {
    console.error('Error loading config:', error)
    throw error
  }
}

export async function saveConfig(settings: FrontendSettings): Promise<void> {
  try {
    // Save hidden categories to user profile (with localStorage fallback)
    await saveUserHiddenCategories(settings.hiddenCategories)
    // Convert frontend format to backend format
    const configData: ConfigData = {
      DEFAULT: {
        selected_model_provider: settings.selectedModelProvider,
        deepseek_api_key: settings.deepseekApiKey,
        deepseek_base_url: settings.deepseekBaseUrl,
        deepseek_model: settings.deepseekModel,
        openai_api_key: settings.openaiApiKey,
        openai_base_url: settings.openaiBaseUrl,
        openai_model: settings.openaiModel,
        glm_api_key: settings.glmApiKey,
        glm_base_url: settings.glmBaseUrl,
        glm_model: settings.glmModel,
        qwen_api_key: settings.qwenApiKey,
        qwen_base_url: settings.qwenBaseUrl,
        qwen_model: settings.qwenModel,
        ollama_api_key: settings.ollamaApiKey,
        ollama_base_url: settings.ollamaBaseUrl,
        ollama_model: settings.ollamaModel,
        local_api_key: settings.localApiKey,
        local_base_url: settings.localBaseUrl,
        local_model: settings.localModel,
        moonshot_api_key: settings.moonshotApiKey,
        moonshot_base_url: settings.moonshotBaseUrl,
        moonshot_model: settings.moonshotModel,
        zhipu_api_key: settings.zhipuApiKey,
        zhipu_base_url: settings.zhipuBaseUrl,
        zhipu_model: settings.zhipuModel,
        cerebras_api_key: settings.cerebrasApiKey,
        cerebras_base_url: settings.cerebrasBaseUrl,
        cerebras_model: settings.cerebrasModel,
        split_use_proxy: settings.splitUseProxy.toString(),
        translate_selected_model_provider: settings.translateSelectedModelProvider,
        translate_deepseek_api_key: settings.translateDeepseekApiKey,
        translate_deepseek_base_url: settings.translateDeepseekBaseUrl,
        translate_deepseek_model: settings.translateDeepseekModel,
        translate_openai_api_key: settings.translateOpenaiApiKey,
        translate_openai_base_url: settings.translateOpenaiBaseUrl,
        translate_openai_model: settings.translateOpenaiModel,
        translate_glm_api_key: settings.translateGlmApiKey,
        translate_glm_base_url: settings.translateGlmBaseUrl,
        translate_glm_model: settings.translateGlmModel,
        translate_qwen_api_key: settings.translateQwenApiKey,
        translate_qwen_base_url: settings.translateQwenBaseUrl,
        translate_qwen_model: settings.translateQwenModel,
        translate_ollama_api_key: settings.translateOllamaApiKey,
        translate_ollama_base_url: settings.translateOllamaBaseUrl,
        translate_ollama_model: settings.translateOllamaModel,
        translate_local_api_key: settings.translateLocalApiKey,
        translate_local_base_url: settings.translateLocalBaseUrl,
        translate_local_model: settings.translateLocalModel,
        translate_moonshot_api_key: settings.translateMoonshotApiKey,
        translate_moonshot_base_url: settings.translateMoonshotBaseUrl,
        translate_moonshot_model: settings.translateMoonshotModel,
        translate_zhipu_api_key: settings.translateZhipuApiKey,
        translate_zhipu_base_url: settings.translateZhipuBaseUrl,
        translate_zhipu_model: settings.translateZhipuModel,
        translate_cerebras_api_key: settings.translateCerebrasApiKey,
        translate_cerebras_base_url: settings.translateCerebrasBaseUrl,
        translate_cerebras_model: settings.translateCerebrasModel,
        translate_use_proxy: settings.translateUseProxy.toString(),
        plain_translate: settings.plainTranslate.toString(),
      },
      'Video watch': {
        raw_language: settings.rawLanguage,
        default_translate_lang: settings.defaultTranslateLang,
      },
      'Subtitle settings': {
        font_family: settings.fontFamily,
        preview_text: settings.previewText,
        font_color: settings.fontColor,
        font_size: settings.fontSize.toString(),
        font_weight: settings.fontWeight,
        background_color: settings.backgroundColor,
        border_radius: settings.borderRadius.toString(),
        text_shadow: settings.textShadow.toString(),
        text_stroke: settings.textStroke.toString(),
        text_stroke_color: settings.textStrokeColor,
        text_stroke_width: settings.textStrokeWidth.toString(),
        background_style: settings.backgroundStyle,
        bottom_distance: settings.bottomDistance.toString(),
      },
      'Foreign Subtitle settings': {
        foreign_font_family: settings.foreignFontFamily,
        foreign_preview_text: settings.foreignPreviewText,
        foreign_font_color: settings.foreignFontColor,
        foreign_font_size: settings.foreignFontSize.toString(),
        foreign_font_weight: settings.foreignFontWeight,
        foreign_background_color: settings.foreignBackgroundColor,
        foreign_border_radius: settings.foreignBorderRadius.toString(),
        foreign_text_shadow: settings.foreignTextShadow.toString(),
        foreign_text_stroke: settings.foreignTextStroke.toString(),
        foreign_text_stroke_color: settings.foreignTextStrokeColor,
        foreign_text_stroke_width: settings.foreignTextStrokeWidth.toString(),
        foreign_background_style: settings.foreignBackgroundStyle,
        foreign_bottom_distance: settings.foreignBottomDistance.toString(),
      },
      'Media Credentials': {
        bilibili_sessdata: settings.bilibiliSessData,
        proxy_url: settings.proxyUrl,
        download_use_proxy: settings.downloadUseProxy.toString(),
      },
      'Transcription Engine': {
        primary_engine: settings.transcriptionPrimaryEngine,
        fwsr_model: settings.fwsrModel,
        use_gpu: settings.useGpu.toString(),
        elevenlabs_api_key: settings.transcriptionElevenlabsApiKey,
        elevenlabs_model: settings.transcriptionElevenlabsModel,
        include_punctuation: settings.transcriptionIncludePunctuation.toString(),
        alibaba_api_key: settings.transcriptionAlibabaApiKey,
        alibaba_model: settings.transcriptionAlibabaModel,
        openai_api_key: settings.transcriptionOpenaiApiKey,
        openai_base_url: settings.transcriptionOpenaiBaseUrl,
      },
      'Remote VidGo Service': {
        host: settings.remoteVidGoHost,
        port: settings.remoteVidGoPort,
        use_ssl: settings.remoteVidGoUseSsl.toString(),
      },
    }

    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/config/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({
        settings: configData,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to save config')
    }
  } catch (error) {
    console.error('Error saving config:', error)
    throw error
  }
}

// Whisper Model Management
export interface WhisperModel {
  name: string
  size: string
  languages: string
  downloaded: boolean
  downloading: boolean
  progress?: number
}

export interface WhisperModelData {
  models: WhisperModel[]
  current_model: string
}

export async function loadWhisperModels(): Promise<WhisperModelData> {
  try {
    const response = await fetch(`${BACKEND}/api/whisper-models/`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to load Whisper models')
    }

    return result.data as WhisperModelData
  } catch (error) {
    console.error('Error loading Whisper models:', error)
    throw error
  }
}

export async function downloadWhisperModel(
  modelName: string,
  engine: string = 'faster_whisper'
): Promise<void> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/whisper-models/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({
        model_name: modelName,
        engine: engine,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to start model download')
    }
  } catch (error) {
    console.error('Error downloading Whisper model:', error)
    throw error
  }
}

export interface ModelProgressData {
  progress: { [modelName: string]: number }
}

export async function getModelDownloadProgress(): Promise<ModelProgressData> {
  try {
    const response = await fetch(`${BACKEND}/api/whisper-models/progress/`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to get model progress')
    }

    return result as ModelProgressData
  } catch (error) {
    console.error('Error getting model download progress:', error)
    throw error
  }
}

export interface ModelSizeData {
  size: number
  size_mb: number
  size_human: string
  file_count: number
  exists: boolean
}

export async function getModelSize(modelName: string): Promise<ModelSizeData> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/whisper-models/size/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({
        model_name: modelName,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to get model size')
    }

    return result as ModelSizeData
  } catch (error) {
    console.error('Error getting model size:', error)
    throw error
  }
}
