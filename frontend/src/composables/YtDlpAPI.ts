/**
 * yt-dlp 包管理 API
 * 对应后端 video/views/yt_dlp.py 的三个接口
 */
import { BACKEND } from './ConfigAPI'
import { getCSRFToken } from './GetCSRFToken'

/** yt-dlp 当前状态 */
export interface YtDlpStatus {
  yt_dlp_version: string
  ejs_version: string
  node_available: boolean
  node_version: string
  node_required_version: string
}

/** 安装依赖结果 */
export interface YtDlpInstallResult {
  success: boolean
  yt_dlp_version: string
  ejs_installed: boolean
  detail: string
}

/** 升级结果 */
export interface YtDlpUpgradeResult {
  success: boolean
  current_version: string
  new_version: string
  upgraded: boolean
  detail: string
}

/** 获取 yt-dlp 当前状态 */
export async function getYtDlpStatus(): Promise<YtDlpStatus> {
  const response = await fetch(`${BACKEND}/api/yt_dlp/status`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  const result = await response.json()
  if (!result.success) {
    throw new Error(result.error || '获取 yt-dlp 状态失败')
  }
  return result.data as YtDlpStatus
}

/** 安装 yt-dlp 依赖（含 EJS 脚本） */
export async function installYtDlpDeps(): Promise<YtDlpInstallResult> {
  const csrf = await getCSRFToken()
  const response = await fetch(`${BACKEND}/api/yt_dlp/install_deps`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrf,
    },
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  return response.json()
}

/** 检测并升级 yt-dlp */
export async function upgradeYtDlp(): Promise<YtDlpUpgradeResult> {
  const csrf = await getCSRFToken()
  const response = await fetch(`${BACKEND}/api/yt_dlp/upgrade`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrf,
    },
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  return response.json()
}
