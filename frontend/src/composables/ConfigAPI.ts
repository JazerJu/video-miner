// Production static files are served by Django/gunicorn on the same origin as the
// API. Only Vite dev needs an explicit backend port.
export const BACKEND =
  import.meta.env.DEV && import.meta.env.VITE_BACKEND_ORIGIN
    ? `${window.location.protocol}//${window.location.hostname}:${import.meta.env.VITE_BACKEND_ORIGIN}`
    : window.location.origin

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
    split_num_threads: string
    enable_split: string
    deepseek_api_key: string
    deepseek_base_url: string
    deepseek_model: string
    openai_api_key: string
    openai_base_url: string
    openai_model: string
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
    volcano_api_key: string
    volcano_base_url: string
    volcano_model: string
    openrouter_api_key: string
    openrouter_base_url: string
    openrouter_model: string
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
    translate_volcano_api_key: string
    translate_volcano_base_url: string
    translate_volcano_model: string
    translate_openrouter_api_key: string
    translate_openrouter_base_url: string
    translate_openrouter_model: string
    translate_cerebras_api_key: string
    translate_cerebras_base_url: string
    translate_cerebras_model: string
    translate_use_proxy: string
    translate_num_threads: string
    enable_translate: string
    plain_translate: string
    hotwords: string
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
    bili_download_use_proxy: string
  }
  'Transcription Engine': {
    primary_engine: string
    vad_backend: string
    fwsr_model: string
    use_gpu: string
    elevenlabs_api_key: string
    elevenlabs_model: string
    include_punctuation: string
  }
  'Video Understanding': {
    vu_thinking_budget: string
    vu_corner_provider: string
    vu_corner_gemini_api_key: string
    vu_corner_gemini_base_url: string
    vu_corner_gemini_model: string
    vu_corner_gemini_official_api_key: string
    vu_corner_gemini_official_base_url: string
    vu_corner_gemini_official_model: string
    vu_corner_mimo_api_key: string
    vu_corner_mimo_base_url: string
    vu_corner_mimo_model: string
    vu_corner_openai_api_key: string
    vu_corner_openai_base_url: string
    vu_corner_openai_model: string
    vu_summary_provider: string
    vu_summary_api_key: string
    vu_summary_base_url: string
    vu_summary_model: string
    vu_knowledge_provider: string
    vu_knowledge_api_key: string
    vu_knowledge_base_url: string
    vu_knowledge_model: string
    vu_corner_use_proxy: string
    vu_corner_coverage: string
    vu_summary_use_proxy: string
    vu_knowledge_use_proxy: string
    vu_download_use_proxy: string
  }
}

export interface FrontendSettings {
  // Split LLM settings
  selectedModelProvider: string
  splitUseProxy: boolean
  splitNumThreads: number
  enableSplit: boolean
  deepseekApiKey: string
  deepseekBaseUrl: string
  deepseekModel: string
  openaiApiKey: string
  openaiBaseUrl: string
  openaiModel: string
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
  volcanoApiKey: string
  volcanoBaseUrl: string
  volcanoModel: string
  openrouterApiKey: string
  openrouterBaseUrl: string
  openrouterModel: string
  cerebrasApiKey: string
  cerebrasBaseUrl: string
  cerebrasModel: string
  // Translate LLM settings
  translateSelectedModelProvider: string
  translateUseProxy: boolean
  translateNumThreads: number
  enableTranslate: boolean
  plainTranslate: boolean
  hotwords: string
  translateDeepseekApiKey: string
  translateDeepseekBaseUrl: string
  translateDeepseekModel: string
  translateOpenaiApiKey: string
  translateOpenaiBaseUrl: string
  translateOpenaiModel: string
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
  translateVolcanoApiKey: string
  translateVolcanoBaseUrl: string
  translateVolcanoModel: string
  translateOpenrouterApiKey: string
  translateOpenrouterBaseUrl: string
  translateOpenrouterModel: string
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
  biliDownloadUseProxy: boolean
  // Transcription Engine settings
  transcriptionPrimaryEngine: string
  vadBackend: string
  fwsrModel: string
  useGpu: boolean  // GPU acceleration toggle
  transcriptionElevenlabsApiKey: string
  transcriptionElevenlabsModel: string
  transcriptionIncludePunctuation: boolean
  // Video Understanding settings
  vuThinkingBudget: string
  vuCornerProvider: string
  vuCornerGeminiApiKey: string
  vuCornerGeminiBaseUrl: string
  vuCornerGeminiModel: string
  vuCornerGeminiOfficialApiKey: string
  vuCornerGeminiOfficialBaseUrl: string
  vuCornerGeminiOfficialModel: string
  vuCornerMimoApiKey: string
  vuCornerMimoBaseUrl: string
  vuCornerMimoModel: string
  vuCornerOpenaiApiKey: string
  vuCornerOpenaiBaseUrl: string
  vuCornerOpenaiModel: string
  vuSummaryProvider: string
  vuSummaryApiKey: string
  vuSummaryBaseUrl: string
  vuSummaryModel: string
  vuKnowledgeProvider: string
  vuKnowledgeApiKey: string
  vuKnowledgeBaseUrl: string
  vuKnowledgeModel: string
  vuCornerUseProxy: boolean
  vuCornerCoverage: number
  vuSummaryUseProxy: boolean
  vuKnowledgeUseProxy: boolean
  vuDownloadUseProxy: boolean
}

export interface BilibiliSessDataValidation {
  checked: boolean
  valid: boolean
  is_login: boolean
  username: string | null
  uid: number | string | null
  bili_code: number | null
  message: string
  error: string | null
}

export interface BilibiliSessDataStatus {
  configured: boolean
  length: number
  expires_at: string | null
  expired: boolean | null
  validation?: BilibiliSessDataValidation
}

async function requestBilibiliSessData(
  method: 'GET' | 'POST' | 'DELETE',
  body?: Record<string, unknown>,
): Promise<BilibiliSessDataStatus> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (method !== 'GET') {
    headers['X-CSRFToken'] = await getCSRFToken()
  }

  const response = await fetch(`${BACKEND}/api/media-credentials/bilibili-sessdata/`, {
    method,
    headers,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const result = await response.json()
  if (!result.success) {
    throw new Error(result.error || 'Bilibili SESSDATA request failed')
  }

  return result.data
}

export async function validateBilibiliSessData(
  sessdata?: string,
): Promise<BilibiliSessDataStatus> {
  const value = sessdata?.trim()
  if (value) {
    await requestBilibiliSessData('POST', { sessdata: value })
  }

  const response = await fetch(`${BACKEND}/api/media-credentials/bilibili-sessdata/?validate=1`, {
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
    throw new Error(result.error || 'Bilibili SESSDATA validation failed')
  }

  return result.data
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
      volcanoApiKey: data.DEFAULT?.volcano_api_key || '',
      volcanoBaseUrl: data.DEFAULT?.volcano_base_url || 'https://ark.cn-beijing.volces.com/api/v3',
      volcanoModel: data.DEFAULT?.volcano_model || 'doubao-seed-2-0-lite-260428',
      openrouterApiKey: data.DEFAULT?.openrouter_api_key || '',
      openrouterBaseUrl: data.DEFAULT?.openrouter_base_url || 'https://openrouter.ai/api/v1',
      openrouterModel: data.DEFAULT?.openrouter_model || 'google/gemini-3-flash',
      cerebrasApiKey: data.DEFAULT?.cerebras_api_key || '',
      cerebrasBaseUrl: data.DEFAULT?.cerebras_base_url || 'https://api.cerebras.ai/v1',
      cerebrasModel: data.DEFAULT?.cerebras_model || 'llama3.1-8b',
      splitUseProxy: data.DEFAULT?.split_use_proxy === 'true',
      splitNumThreads: parseInt(data.DEFAULT?.split_num_threads || '8', 10),
      enableSplit: data.DEFAULT?.enable_split !== 'false',
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
      translateVolcanoApiKey: data.DEFAULT?.translate_volcano_api_key || '',
      translateVolcanoBaseUrl: data.DEFAULT?.translate_volcano_base_url || 'https://ark.cn-beijing.volces.com/api/v3',
      translateVolcanoModel: data.DEFAULT?.translate_volcano_model || 'doubao-seed-2-0-lite-260428',
      translateOpenrouterApiKey: data.DEFAULT?.translate_openrouter_api_key || '',
      translateOpenrouterBaseUrl: data.DEFAULT?.translate_openrouter_base_url || 'https://openrouter.ai/api/v1',
      translateOpenrouterModel: data.DEFAULT?.translate_openrouter_model || 'google/gemini-3-flash',
      translateCerebrasApiKey: data.DEFAULT?.translate_cerebras_api_key || '',
      translateCerebrasBaseUrl: data.DEFAULT?.translate_cerebras_base_url || 'https://api.cerebras.ai/v1',
      translateCerebrasModel: data.DEFAULT?.translate_cerebras_model || 'llama3.1-8b',
      translateUseProxy: data.DEFAULT?.translate_use_proxy === 'true',
      translateNumThreads: parseInt(data.DEFAULT?.translate_num_threads || '8', 10),
      enableTranslate: data.DEFAULT?.enable_translate !== 'false',
      plainTranslate: data.DEFAULT?.plain_translate === 'true',
      hotwords: data.DEFAULT?.hotwords || '',
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
      biliDownloadUseProxy: data['Media Credentials']?.bili_download_use_proxy === 'true',
      // Transcription Engine settings
      transcriptionPrimaryEngine: data['Transcription Engine']?.primary_engine || 'funasr_gguf',
      vadBackend: data['Transcription Engine']?.vad_backend || 'silero',
      fwsrModel: data['Transcription Engine']?.fwsr_model || 'large-v3',
      useGpu: data['Transcription Engine']?.use_gpu === 'true',
      transcriptionElevenlabsApiKey: data['Transcription Engine']?.elevenlabs_api_key || '',
      transcriptionElevenlabsModel: data['Transcription Engine']?.elevenlabs_model || 'scribe_v1',
      transcriptionIncludePunctuation: data['Transcription Engine']?.include_punctuation === 'true',
      // Video Understanding settings
      vuThinkingBudget: data['Video Understanding']?.vu_thinking_budget || 'low',
      vuCornerProvider: data['Video Understanding']?.vu_corner_provider || 'gemini',
      vuCornerGeminiApiKey: data['Video Understanding']?.vu_corner_gemini_api_key || '',
      vuCornerGeminiBaseUrl:
        data['Video Understanding']?.vu_corner_gemini_base_url || 'https://openrouter.ai/api/v1',
      vuCornerGeminiModel:
        data['Video Understanding']?.vu_corner_gemini_model || 'google/gemini-2.5-flash',
      vuCornerGeminiOfficialApiKey: data['Video Understanding']?.vu_corner_gemini_official_api_key || '',
      vuCornerGeminiOfficialBaseUrl:
        data['Video Understanding']?.vu_corner_gemini_official_base_url || 'https://generativelanguage.googleapis.com/v1beta/openai',
      vuCornerGeminiOfficialModel:
        data['Video Understanding']?.vu_corner_gemini_official_model || 'gemini-2.5-flash',
      vuCornerMimoApiKey: data['Video Understanding']?.vu_corner_mimo_api_key || '',
      vuCornerMimoBaseUrl: data['Video Understanding']?.vu_corner_mimo_base_url || '',
      vuCornerMimoModel: data['Video Understanding']?.vu_corner_mimo_model || 'mimo-v2.5',
      vuCornerOpenaiApiKey: data['Video Understanding']?.vu_corner_openai_api_key || '',
      vuCornerOpenaiBaseUrl: data['Video Understanding']?.vu_corner_openai_base_url || '',
      vuCornerOpenaiModel: data['Video Understanding']?.vu_corner_openai_model || '',
      vuSummaryProvider: data['Video Understanding']?.vu_summary_provider || 'deepseek',
      vuSummaryApiKey: data['Video Understanding']?.vu_summary_api_key || '',
      vuSummaryBaseUrl:
        data['Video Understanding']?.vu_summary_base_url || 'https://api.deepseek.com',
      vuSummaryModel: data['Video Understanding']?.vu_summary_model || 'deepseek-chat',
      vuKnowledgeProvider: data['Video Understanding']?.vu_knowledge_provider || 'doubao',
      vuKnowledgeApiKey: data['Video Understanding']?.vu_knowledge_api_key || '',
      vuKnowledgeBaseUrl: data['Video Understanding']?.vu_knowledge_base_url || '',
      vuKnowledgeModel: data['Video Understanding']?.vu_knowledge_model || '',
      vuCornerUseProxy: data['Video Understanding']?.vu_corner_use_proxy === 'true',
      vuCornerCoverage: parseFloat(data['Video Understanding']?.vu_corner_coverage || '0.6'),
      vuSummaryUseProxy: data['Video Understanding']?.vu_summary_use_proxy === 'true',
      vuKnowledgeUseProxy: data['Video Understanding']?.vu_knowledge_use_proxy === 'true',
      vuDownloadUseProxy: data['Video Understanding']?.vu_download_use_proxy === 'true',
    }
  } catch (error) {
    console.error('Error loading config:', error)
    throw error
  }
}

export const loadSettings = loadConfig

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
        volcano_api_key: settings.volcanoApiKey,
        volcano_base_url: settings.volcanoBaseUrl,
        volcano_model: settings.volcanoModel,
        openrouter_api_key: settings.openrouterApiKey,
        openrouter_base_url: settings.openrouterBaseUrl,
        openrouter_model: settings.openrouterModel,
        cerebras_api_key: settings.cerebrasApiKey,
        cerebras_base_url: settings.cerebrasBaseUrl,
        cerebras_model: settings.cerebrasModel,
split_use_proxy: settings.splitUseProxy.toString(),
      split_num_threads: settings.splitNumThreads.toString(),
      enable_split: settings.enableSplit.toString(),
        translate_selected_model_provider: settings.translateSelectedModelProvider,
        translate_deepseek_api_key: settings.translateDeepseekApiKey,
        translate_deepseek_base_url: settings.translateDeepseekBaseUrl,
        translate_deepseek_model: settings.translateDeepseekModel,
        translate_openai_api_key: settings.translateOpenaiApiKey,
        translate_openai_base_url: settings.translateOpenaiBaseUrl,
        translate_openai_model: settings.translateOpenaiModel,
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
        translate_volcano_api_key: settings.translateVolcanoApiKey,
        translate_volcano_base_url: settings.translateVolcanoBaseUrl,
        translate_volcano_model: settings.translateVolcanoModel,
        translate_openrouter_api_key: settings.translateOpenrouterApiKey,
        translate_openrouter_base_url: settings.translateOpenrouterBaseUrl,
        translate_openrouter_model: settings.translateOpenrouterModel,
        translate_cerebras_api_key: settings.translateCerebrasApiKey,
        translate_cerebras_base_url: settings.translateCerebrasBaseUrl,
        translate_cerebras_model: settings.translateCerebrasModel,
        translate_use_proxy: settings.translateUseProxy.toString(),
        translate_num_threads: settings.translateNumThreads.toString(),
        enable_translate: settings.enableTranslate.toString(),
        plain_translate: settings.plainTranslate.toString(),
        hotwords: settings.hotwords,
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
    bili_download_use_proxy: settings.biliDownloadUseProxy.toString(),
      },
      'Transcription Engine': {
        primary_engine: settings.transcriptionPrimaryEngine,
    vad_backend: settings.vadBackend,
        fwsr_model: settings.fwsrModel,
        use_gpu: settings.useGpu.toString(),
        elevenlabs_api_key: settings.transcriptionElevenlabsApiKey,
        elevenlabs_model: settings.transcriptionElevenlabsModel,
        include_punctuation: settings.transcriptionIncludePunctuation.toString(),
      },
      'Video Understanding': {
        vu_thinking_budget: settings.vuThinkingBudget,
        vu_corner_provider: settings.vuCornerProvider,
        vu_corner_gemini_api_key: settings.vuCornerGeminiApiKey,
        vu_corner_gemini_base_url: settings.vuCornerGeminiBaseUrl,
        vu_corner_gemini_model: settings.vuCornerGeminiModel,
        vu_corner_gemini_official_api_key: settings.vuCornerGeminiOfficialApiKey,
        vu_corner_gemini_official_base_url: settings.vuCornerGeminiOfficialBaseUrl,
        vu_corner_gemini_official_model: settings.vuCornerGeminiOfficialModel,
        vu_corner_mimo_api_key: settings.vuCornerMimoApiKey,
        vu_corner_mimo_base_url: settings.vuCornerMimoBaseUrl,
        vu_corner_mimo_model: settings.vuCornerMimoModel,
        vu_corner_openai_api_key: settings.vuCornerOpenaiApiKey,
        vu_corner_openai_base_url: settings.vuCornerOpenaiBaseUrl,
        vu_corner_openai_model: settings.vuCornerOpenaiModel,
        vu_summary_provider: settings.vuSummaryProvider,
        vu_summary_api_key: settings.vuSummaryApiKey,
        vu_summary_base_url: settings.vuSummaryBaseUrl,
        vu_summary_model: settings.vuSummaryModel,
        vu_knowledge_provider: settings.vuKnowledgeProvider,
        vu_knowledge_api_key: settings.vuKnowledgeApiKey,
        vu_knowledge_base_url: settings.vuKnowledgeBaseUrl,
        vu_knowledge_model: settings.vuKnowledgeModel,
        vu_corner_use_proxy: settings.vuCornerUseProxy.toString(),
        vu_corner_coverage: settings.vuCornerCoverage.toString(),
        vu_summary_use_proxy: settings.vuSummaryUseProxy.toString(),
        vu_knowledge_use_proxy: settings.vuKnowledgeUseProxy.toString(),
        vu_download_use_proxy: settings.vuDownloadUseProxy.toString(),
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
  engine: string = 'funasr_gguf'
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

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1)
  return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i]
}

export type VidUnderModelStatus = 'not_downloaded' | 'downloading' | 'downloaded' | 'error'
export type VidUnderModelSource = 'hf' | 'modelscope'

export interface VidUnderModel {
  name: string
  label: string
  description: string
  total_size?: number
  totalSize?: number
  downloaded_size?: number
  downloaded?: boolean
  downloading?: boolean
  progress?: number
  status?: VidUnderModelStatus
  file_count?: number
  error?: string
}

export interface VidUnderProgress {
  [modelName: string]: {
    current: number
    total: number
    percent: number
    status: string
    current_file?: string
    error?: string
    force?: boolean
  }
}

export interface VidUnderModelData {
  models: VidUnderModel[]
}

export async function loadVidUnderModels(): Promise<VidUnderModel[]> {
  try {
    const response = await fetch(`${BACKEND}/api/vidunder-models/`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to load vidUnder models')
    }

    return (result.data?.models || result.models || []) as VidUnderModel[]
  } catch (error) {
    console.error('Error loading vidUnder models:', error)
    throw error
  }
}

export async function downloadVidUnderModel(
  modelName: string,
  source: VidUnderModelSource = 'hf',
  useProxy = false,
  proxy?: string,
  force = false,
): Promise<void> {
  try {
    const csrf = await getCSRFToken()
    const body: Record<string, string | boolean> = {
      model_name: modelName,
      source,
      use_proxy: useProxy,
      force,
    }
    if (proxy) body.proxy = proxy
    const response = await fetch(`${BACKEND}/api/vidunder-models/download/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to start vidUnder model download')
    }
  } catch (error) {
    console.error('Error downloading vidUnder model:', error)
    throw error
  }
}

export async function getVidUnderDownloadProgress(): Promise<VidUnderProgress> {
  try {
    const response = await fetch(`${BACKEND}/api/vidunder-models/progress/`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()

    if (!result.success) {
      throw new Error(result.error || 'Failed to get vidUnder model progress')
    }

    return (result.data?.progress || result.progress || {}) as VidUnderProgress
  } catch (error) {
    console.error('Error getting vidUnder model progress:', error)
    throw error
  }
}

export const getVidUnderProgress = getVidUnderDownloadProgress
