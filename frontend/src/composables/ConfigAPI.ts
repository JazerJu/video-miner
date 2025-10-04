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
    enable_thinking: string
    use_proxy: string
    deepseek_api_key: string
    deepseek_base_url: string
    glm_api_key: string
    glm_base_url: string
    openai_api_key: string
    openai_base_url: string
    qwen_api_key: string
    qwen_base_url: string
  }
  'Video watch': {
    raw_language: string
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
  }
  'Transcription Engine': {
    primary_engine: string
    fallback_engine: string
    transcription_mode: string
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
  // Model settings
  selectedModelProvider: string
  enableThinking: boolean
  useProxy: boolean
  // Provider-specific API keys
  deepseekApiKey: string
  deepseekBaseUrl: string
  openaiApiKey: string
  openaiBaseUrl: string
  glmApiKey: string
  glmBaseUrl: string
  qwenApiKey: string
  qwenBaseUrl: string
  // Interface settings
  rawLanguage: string
  hiddenCategories: number[] // 新增：隐藏的分类ID列表
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
  // Media credentials
  bilibiliSessData: string
  // Transcription Engine settings
  transcriptionPrimaryEngine: string
  transcriptionFallbackEngine: string
  transcriptionMode: string
  fwsrModel: string
  useGpu: boolean  // 🆕 GPU acceleration toggle
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
      // Model settings
      selectedModelProvider: data.DEFAULT?.selected_model_provider || 'deepseek',
      enableThinking: data.DEFAULT?.enable_thinking === 'true',
      // Provider-specific API keys
      deepseekApiKey: data.DEFAULT?.deepseek_api_key || '',
      deepseekBaseUrl: data.DEFAULT?.deepseek_base_url || 'https://api.deepseek.com',
      openaiApiKey: data.DEFAULT?.openai_api_key || '',
      openaiBaseUrl: data.DEFAULT?.openai_base_url || 'https://api.chatanywhere.tech/v1',
      glmApiKey: data.DEFAULT?.glm_api_key || '',
      glmBaseUrl: data.DEFAULT?.glm_base_url || 'https://api.deepseek.com',
      qwenApiKey: data.DEFAULT?.qwen_api_key || '',
      qwenBaseUrl:
        data.DEFAULT?.qwen_base_url || 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      useProxy: data.DEFAULT?.use_proxy === 'true',
      // Interface settings
      rawLanguage: data['Video watch']?.raw_language || 'zh',
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
      // Media credentials
      bilibiliSessData: data['Media Credentials']?.bilibili_sessdata || '',
      // Transcription Engine settings
      transcriptionMode: data['Transcription Engine']?.transcription_mode || 'local',
      transcriptionPrimaryEngine: data['Transcription Engine']?.primary_engine || 'whisper_cpp',
      transcriptionFallbackEngine: data['Transcription Engine']?.fallback_engine || '',
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
        enable_thinking: settings.enableThinking.toString(),
        deepseek_api_key: settings.deepseekApiKey,
        deepseek_base_url: settings.deepseekBaseUrl,
        openai_api_key: settings.openaiApiKey,
        openai_base_url: settings.openaiBaseUrl,
        glm_api_key: settings.glmApiKey,
        glm_base_url: settings.glmBaseUrl,
        qwen_api_key: settings.qwenApiKey,
        qwen_base_url: settings.qwenBaseUrl,
        use_proxy: settings.useProxy.toString(),
      },
      'Video watch': {
        raw_language: settings.rawLanguage,
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
      },
      'Transcription Engine': {
        transcription_mode: settings.transcriptionMode,
        primary_engine: settings.transcriptionPrimaryEngine,
        fallback_engine: settings.transcriptionFallbackEngine,
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
