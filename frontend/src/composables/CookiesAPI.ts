/**
 * YouTube cookies.txt 管理 API
 * 对应后端 video/views/cookies.py
 */
import { BACKEND } from './ConfigAPI'
import { getCSRFToken } from './GetCSRFToken'

export interface CookiesStatus {
  exists: boolean
  filename?: string
  last_modified?: string
  file_size?: number
}

export interface CookiesUploadResult {
  success: boolean
  filename: string
  last_modified: string
  error?: string
}

/** 获取 cookies.txt 状态（是否存在、修改时间） */
export async function getYoutubeCookiesStatus(): Promise<CookiesStatus> {
  const response = await fetch(`${BACKEND}/api/cookies/youtube/status`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  return response.json()
}

/** 上传 cookies.txt（覆盖旧的） */
export async function uploadYoutubeCookies(file: File): Promise<CookiesUploadResult> {
  const csrf = await getCSRFToken()
  const formData = new FormData()
  formData.append('cookies_file', file)

  const response = await fetch(`${BACKEND}/api/cookies/youtube/upload`, {
    method: 'POST',
    headers: { 'X-CSRFToken': csrf },
    credentials: 'include',
    body: formData,
  })
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  return response.json()
}
