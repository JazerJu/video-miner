// 字幕样式：原文、译文各一套设置。播放器把原文、译文画成两层字幕，各自套用这里的样式
import { ref, computed } from 'vue'
import { loadConfig } from './ConfigAPI'
import { fontFamilyCSS, loadUploadedFonts } from './SubtitleFonts'

// 字幕样式类型定义
export interface SubtitleStyleSettings {
  fontFamily: string
  fontColor: string
  fontSize: number
  fontWeight: string
  backgroundStyle: 'none' | 'solid' | 'semi-transparent' // 合并背景设置
  backgroundColor: string
  borderRadius: number
  textShadow: boolean
  textStroke: boolean // 新增：文字描边效果
  textStrokeColor: string // 新增：描边颜色
  textStrokeWidth: number // 新增：描边宽度
  bottomDistance: number // 新增：距底边距离（像素）
}

// 外文字幕样式类型定义
interface ForeignSubtitleStyleSettings {
  fontFamily: string
  fontColor: string
  fontSize: number
  fontWeight: string
  backgroundStyle: 'none' | 'solid' | 'semi-transparent'
  backgroundColor: string
  borderRadius: number
  textShadow: boolean
  textStroke: boolean // 新增：文字描边效果
  textStrokeColor: string // 新增：描边颜色
  textStrokeWidth: number // 新增：描边宽度
  bottomDistance: number
}

// 全局字幕样式状态 (原文字幕)
const subtitleSettings = ref<SubtitleStyleSettings>({
  fontFamily: '宋体',
  fontColor: '#ea9749',
  fontSize: 18,
  fontWeight: '400',
  backgroundStyle: 'semi-transparent', // 默认半透明背景
  backgroundColor: '#000000',
  borderRadius: 4,
  textShadow: false,
  textStroke: false, // 默认不开启描边
  textStrokeColor: '#000000', // 默认黑色描边
  textStrokeWidth: 2, // 默认描边宽度2px
  bottomDistance: 80, // 默认距离底边80像素
})

// 外文字幕样式状态
const foreignSubtitleSettings = ref<ForeignSubtitleStyleSettings>({
  fontFamily: 'Arial',
  fontColor: '#ffffff',
  fontSize: 16,
  fontWeight: '400',
  backgroundStyle: 'semi-transparent',
  backgroundColor: '#000000',
  borderRadius: 4,
  textShadow: false,
  textStroke: false, // 默认不开启描边
  textStrokeColor: '#000000', // 默认黑色描边
  textStrokeWidth: 2, // 默认描边宽度2px
  bottomDistance: 120, // 默认距离底边120像素，避免与原文重叠
})

// 全屏状态检测
const isFullscreen = ref(false)

// 监听全屏状态变化
const updateFullscreenState = () => {
  isFullscreen.value = !!(document.fullscreenElement || (document as any).webkitFullscreenElement)
}

// 计算背景颜色
const getBackgroundColor = (style: string, color: string) => {
  switch (style) {
    case 'none':
      return 'transparent'
    case 'solid':
      return color
    case 'semi-transparent':
      // 将hex颜色转换为rgba，透明度0.8
      const hex = color.replace('#', '')
      const r = parseInt(hex.substring(0, 2), 16)
      const g = parseInt(hex.substring(2, 4), 16)
      const b = parseInt(hex.substring(4, 6), 16)
      return `rgba(${r}, ${g}, ${b}, 0.8)`
    default:
      return 'transparent'
  }
}

// 生成文字描边样式（使用多重text-shadow模拟描边效果）
const getTextStroke = (enabled: boolean, color: string, width: number) => {
  if (!enabled) return 'none'

  // 使用多重text-shadow创建描边效果，比-webkit-text-stroke兼容性更好
  const shadows = []
  for (let x = -width; x <= width; x++) {
    for (let y = -width; y <= width; y++) {
      if (x === 0 && y === 0) continue // 跳过中心点
      shadows.push(`${x}px ${y}px 0 ${color}`)
    }
  }
  return shadows.join(', ')
}

// 结合text-shadow和text-stroke效果；scale 是字幕层随播放器尺寸的缩放比例
const getCombinedTextShadow = (
  textShadow: boolean,
  textStroke: boolean,
  strokeColor: string,
  strokeWidth: number,
  scale = 1,
) => {
  const effects = []

  // 添加描边效果
  if (textStroke) {
    const strokeEffect = getTextStroke(true, strokeColor, Math.max(1, Math.round(strokeWidth * scale)))
    if (strokeEffect !== 'none') {
      effects.push(strokeEffect)
    }
  }

  // 添加阴影效果
  if (textShadow) {
    const px = (value: number) => `${Math.round(value * scale * 100) / 100}px`
    effects.push(`${px(2)} ${px(2)} ${px(4)} rgba(0,0,0,0.5)`)
  }

  return effects.length > 0 ? effects.join(', ') : 'none'
}

// CSS变量样式字符串 (原文字幕)
const subtitleCSSVars = computed(() => ({
  '--subtitle-font-family': subtitleSettings.value.fontFamily,
  '--subtitle-color': subtitleSettings.value.fontColor,
  '--subtitle-font-size': `${subtitleSettings.value.fontSize}px`,
  '--subtitle-font-weight': subtitleSettings.value.fontWeight,
  '--subtitle-background-color': getBackgroundColor(
    subtitleSettings.value.backgroundStyle,
    subtitleSettings.value.backgroundColor,
  ),
  '--subtitle-border-radius': `${subtitleSettings.value.borderRadius}px`,
  '--subtitle-text-shadow': subtitleSettings.value.textShadow
    ? '2px 2px 4px rgba(0,0,0,0.5)'
    : 'none',
  '--subtitle-text-stroke': getTextStroke(
    subtitleSettings.value.textStroke,
    subtitleSettings.value.textStrokeColor,
    subtitleSettings.value.textStrokeWidth,
  ),
  '--subtitle-bottom-distance': `${subtitleSettings.value.bottomDistance}px`,
}))

// CSS变量样式字符串 (外文字幕)
const foreignSubtitleCSSVars = computed(() => ({
  '--foreign-subtitle-font-family': foreignSubtitleSettings.value.fontFamily,
  '--foreign-subtitle-color': foreignSubtitleSettings.value.fontColor,
  '--foreign-subtitle-font-size': `${foreignSubtitleSettings.value.fontSize}px`,
  '--foreign-subtitle-font-weight': foreignSubtitleSettings.value.fontWeight,
  '--foreign-subtitle-background-color': getBackgroundColor(
    foreignSubtitleSettings.value.backgroundStyle,
    foreignSubtitleSettings.value.backgroundColor,
  ),
  '--foreign-subtitle-border-radius': `${foreignSubtitleSettings.value.borderRadius}px`,
  '--foreign-subtitle-text-shadow': foreignSubtitleSettings.value.textShadow
    ? '2px 2px 4px rgba(0,0,0,0.5)'
    : 'none',
  '--foreign-subtitle-text-stroke': getTextStroke(
    foreignSubtitleSettings.value.textStroke,
    foreignSubtitleSettings.value.textStrokeColor,
    foreignSubtitleSettings.value.textStrokeWidth,
  ),
  '--foreign-subtitle-bottom-distance': `${foreignSubtitleSettings.value.bottomDistance}px`,
}))

// 字幕设置里的字号、边距、距底边距离都按 600px 高的播放器来定。
// 播放器变大变小（全屏、窄窗口、字幕编辑页）时按高度等比缩放，字幕和画面的比例保持不变；
// 缩放限制在 0.6 到 2.5 倍之间，窗口很小时字也还看得清。
export const SUBTITLE_REFERENCE_PLAYER_HEIGHT = 600

export function subtitleScaleFor(playerHeight: number) {
  if (!playerHeight || playerHeight <= 0) return 1
  return Math.min(2.5, Math.max(0.6, playerHeight / SUBTITLE_REFERENCE_PLAYER_HEIGHT))
}

// 播放器字幕层的文字样式：背景只包住文字，折行后每行各自带背景。
// 以前是往 video.js 的字幕容器上注入 CSS、按容器属性区分原文和译文，容器只有一个，双语时两种文字只能共用一套样式。
export function subtitleTextStyle(settings: SubtitleStyleSettings, scale = 1) {
  const px = (value: number) => `${Math.round(value * scale * 100) / 100}px`
  const paddingY = settings.backgroundStyle === 'none' ? 2 : 4
  const paddingX = settings.backgroundStyle === 'none' ? 4 : 8
  return {
    fontFamily: fontFamilyCSS(settings.fontFamily),
    color: settings.fontColor,
    fontSize: px(settings.fontSize),
    fontWeight: settings.fontWeight,
    backgroundColor: getBackgroundColor(settings.backgroundStyle, settings.backgroundColor),
    borderRadius: px(settings.borderRadius),
    padding: `${px(paddingY)} ${px(paddingX)}`,
    textShadow: getCombinedTextShadow(
      settings.textShadow,
      settings.textStroke,
      settings.textStrokeColor,
      settings.textStrokeWidth,
      scale,
    ),
  }
}

// 设置全屏状态监听器
if (typeof document !== 'undefined') {
  document.addEventListener('fullscreenchange', updateFullscreenState)
  document.addEventListener('webkitfullscreenchange', updateFullscreenState)
  window.addEventListener('resize', updateFullscreenState)
}

// 从配置加载字幕样式
async function loadSubtitleSettings() {
  // 已上传的字体要先注册成 @font-face 字幕里才用得上，不必等它加载完
  void loadUploadedFonts()
  try {
    const config = await loadConfig()

    // 加载原文字幕设置
    subtitleSettings.value = {
      fontFamily: config.fontFamily || '宋体',
      fontColor: config.fontColor || '#ea9749',
      fontSize: config.fontSize || 18,
      fontWeight: config.fontWeight || '400',
      backgroundStyle: config.backgroundStyle || 'semi-transparent',
      backgroundColor: config.backgroundColor || '#000000',
      borderRadius: config.borderRadius || 4,
      textShadow: config.textShadow ?? false,
      textStroke: config.textStroke ?? false,
      textStrokeColor: config.textStrokeColor || '#000000',
      textStrokeWidth: config.textStrokeWidth || 2,
      bottomDistance: config.bottomDistance || 80,
    }

    // 加载外文字幕设置
    foreignSubtitleSettings.value = {
      fontFamily: config.foreignFontFamily || 'Arial',
      fontColor: config.foreignFontColor || '#ffffff',
      fontSize: config.foreignFontSize || 16,
      fontWeight: config.foreignFontWeight || '400',
      backgroundStyle: config.foreignBackgroundStyle || 'semi-transparent',
      backgroundColor: config.foreignBackgroundColor || '#000000',
      borderRadius: config.foreignBorderRadius || 4,
      textShadow: config.foreignTextShadow ?? false,
      textStroke: config.foreignTextStroke ?? false,
      textStrokeColor: config.foreignTextStrokeColor || '#000000',
      textStrokeWidth: config.foreignTextStrokeWidth || 2,
      bottomDistance: config.foreignBottomDistance || 120,
    }

    console.log('[SubtitleStyle] Loaded raw subtitle settings:', subtitleSettings.value)
    console.log('[SubtitleStyle] Loaded foreign subtitle settings:', foreignSubtitleSettings.value)
  } catch (error) {
    console.error('[SubtitleStyle] Failed to load subtitle settings:', error)
  }
}

// 更新原文字幕样式
function updateSubtitleSettings(newSettings: Partial<typeof subtitleSettings.value>) {
  Object.assign(subtitleSettings.value, newSettings)
  console.log('[SubtitleStyle] Updated raw subtitle settings:', subtitleSettings.value)
}

// 更新外文字幕样式
function updateForeignSubtitleSettings(newSettings: Partial<typeof foreignSubtitleSettings.value>) {
  Object.assign(foreignSubtitleSettings.value, newSettings)
  console.log('[SubtitleStyle] Updated foreign subtitle settings:', foreignSubtitleSettings.value)
}

// 清理函数
function cleanup() {
  // 移除事件监听器
  if (typeof document !== 'undefined') {
    document.removeEventListener('fullscreenchange', updateFullscreenState)
    document.removeEventListener('webkitfullscreenchange', updateFullscreenState)
    window.removeEventListener('resize', updateFullscreenState)
  }
}

export function useSubtitleStyle() {
  return {
    // 原文字幕相关
    subtitleSettings: subtitleSettings,
    subtitleCSSVars,
    updateSubtitleSettings,
    // 外文字幕相关
    foreignSubtitleSettings: foreignSubtitleSettings,
    foreignSubtitleCSSVars,
    updateForeignSubtitleSettings,
    subtitleTextStyle,
    subtitleScaleFor,
    // 通用功能
    isFullscreen,
    loadSubtitleSettings,
    updateFullscreenState,
    cleanup,
  }
}
