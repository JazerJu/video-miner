// 字幕字体：服务器上已上传的字体，以及本机已安装字体的检测。
// 上传的字体由后端 /api/subtitle-fonts/ 管理，这里注册成 @font-face，任何设备打开 VidGo 都能用；
// 本机字体只要写对名字，但只在装了它的设备上生效。
import { computed, ref } from 'vue'
import { BACKEND } from './ConfigAPI'
import { getCSRFToken } from './GetCSRFToken'

export interface UploadedFont {
  file: string
  family: string
  weight: string
  style: string
  format: string
  size: number
  url: string
}

export const PRESET_FONT_FAMILIES = ['宋体', '微软雅黑', 'Arial', 'Times New Roman', 'Helvetica']

const uploadedFonts = ref<UploadedFont[]>([])
const uploadedFontFamilies = computed(() => [...new Set(uploadedFonts.value.map((font) => font.family))])
let loading: Promise<UploadedFont[]> | null = null
let fontFaceStyle: HTMLStyleElement | null = null
let measureContext: CanvasRenderingContext2D | null = null

function cssString(value: string) {
  return `"${value.replace(/[\\"]/g, '\\$&').replace(/[\r\n\f]+/g, ' ')}"`
}

/** 字体名写进 CSS 前加引号，避免带空格、数字开头的名字失效；已经是字体栈的原样返回 */
export function fontFamilyCSS(name: string | null | undefined) {
  const family = (name ?? '').trim()
  if (!family) return ''
  return /[,"']/.test(family) ? family : cssString(family)
}

function registerFontFaces(fonts: UploadedFont[]) {
  if (typeof document === 'undefined') return
  if (!fontFaceStyle) {
    fontFaceStyle = document.createElement('style')
    fontFaceStyle.id = 'vidgo-subtitle-fonts'
    document.head.appendChild(fontFaceStyle)
  }
  fontFaceStyle.textContent = fonts
    .map(
      (font) =>
        `@font-face { font-family: ${cssString(font.family)}; src: url(${cssString(BACKEND + font.url)}) format(${cssString(font.format)}); font-weight: ${font.weight}; font-style: ${font.style}; font-display: swap; }`,
    )
    .join('\n')
}

/** 拉取已上传字体并注册 @font-face。多个组件同时调用时共用一次请求；force 用于上传、删除之后刷新 */
export function loadUploadedFonts(force = false): Promise<UploadedFont[]> {
  if (loading && !force) return loading
  const request = (async () => {
    const res = await fetch(`${BACKEND}/api/subtitle-fonts/`, { credentials: 'include' })
    const data = await res.json()
    if (!res.ok || !data.success) throw new Error(data.error || `HTTP ${res.status}`)
    uploadedFonts.value = data.fonts
    registerFontFaces(data.fonts)
    return uploadedFonts.value
  })()
  loading = request.catch((error) => {
    console.error('[SubtitleFonts] Failed to load uploaded fonts:', error)
    loading = null
    return uploadedFonts.value
  })
  return loading
}

async function errorMessage(res: Response) {
  try {
    const data = await res.json()
    return data.error || `HTTP ${res.status}`
  } catch {
    return `HTTP ${res.status}`
  }
}

export async function uploadSubtitleFont(file: File): Promise<UploadedFont> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${BACKEND}/api/subtitle-fonts/`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-CSRFToken': await getCSRFToken() },
    body,
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  const data = await res.json()
  await loadUploadedFonts(true)
  return data.font
}

export async function deleteSubtitleFont(file: string): Promise<void> {
  const res = await fetch(`${BACKEND}/api/subtitle-fonts/${encodeURIComponent(file)}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: { 'X-CSRFToken': await getCSRFToken() },
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  await loadUploadedFonts(true)
}

/** 浏览器能否列出本机字体：Chromium 的 Local Font Access API，只在 HTTPS 或 localhost 下可用，首次会弹权限请求 */
export function canListLocalFonts() {
  return typeof window !== 'undefined' && window.isSecureContext && 'queryLocalFonts' in window
}

export async function listLocalFontFamilies(): Promise<string[]> {
  const fonts: Array<{ family: string }> = await (window as any).queryLocalFonts()
  return [...new Set(fonts.map((font) => font.family))].sort((a, b) => a.localeCompare(b, 'zh-CN'))
}

/**
 * 用画布量宽度判断这台设备能不能渲染某个字体。
 * 和 monospace、serif、sans-serif 三种通用字体量出来都一样宽，说明浏览器找不到它，退回了默认字体。
 */
export function isFontRenderable(name: string): boolean {
  const family = name.trim()
  if (!family || typeof document === 'undefined') return false
  measureContext ??= document.createElement('canvas').getContext('2d')
  if (!measureContext) return true
  const context = measureContext
  const sample = 'mmmmmmmmmmlli WwQq 0123 永和九年岁在癸丑'
  return ['monospace', 'serif', 'sans-serif'].some((generic) => {
    context.font = `72px ${generic}`
    const fallbackWidth = context.measureText(sample).width
    context.font = `72px ${fontFamilyCSS(family)}, ${generic}`
    return context.measureText(sample).width !== fallbackWidth
  })
}

export function useSubtitleFonts() {
  return {
    uploadedFonts,
    uploadedFontFamilies,
    loadUploadedFonts,
    uploadSubtitleFont,
    deleteSubtitleFont,
    canListLocalFonts,
    listLocalFontFamilies,
    isFontRenderable,
  }
}
