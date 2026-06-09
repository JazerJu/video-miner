const BACKEND = ''

export interface ResolvedStream {
  platform: 'youtube' | 'bilibili'
  title: string
  duration: number
  thumbnail: string
  video: {
    url: string
    format_id: string
    height: number
    ext?: string
    protocol?: string
    has_audio?: boolean
    requires_relay: boolean
    headers: Record<string, string>
  }
  audio: {
    url: string
    format_id: string
    ext?: string
    protocol?: string
    language?: string
    requires_relay: boolean
    headers: Record<string, string>
  }
}

export interface TranscriptionSegment {
  index: number
  text: string
  start: number
  end: number
  translation?: string
}

export async function resolveStream(url: string): Promise<ResolvedStream> {
  const resp = await fetch(`${BACKEND}/api/stream_transcription/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    credentials: 'include',
  })
  const data = await resp.json()
  if (!resp.ok || !data.success) throw new Error(data.error || data.message || 'Resolve failed')
  return data
}

export function getRelayedUrl(originalUrl: string, headers: Record<string, string> = {}): string {
  const params = new URLSearchParams({ url: originalUrl })
  if (headers.Referer || headers.referer) {
    params.set('referer', headers.Referer || headers.referer)
  }
  if (headers['User-Agent'] || headers.userAgent || headers['user-agent']) {
    params.set(
      'user_agent',
      headers['User-Agent'] || headers.userAgent || headers['user-agent'],
    )
  }
  return `${BACKEND}/api/stream_transcription/proxy?${params.toString()}`
}

export async function startTranscription(
  audioUrl: string,
  audioHeaders: Record<string, string> = {},
  requiresRelay = false,
  sourceLang = 'en',
  targetLang = '',
): Promise<string> {
  const body: Record<string, unknown> = {
    audio_url: audioUrl,
    audio_headers: audioHeaders,
    requires_relay: requiresRelay,
    source_lang: sourceLang,
  }
  if (targetLang) body.target_lang = targetLang
  const resp = await fetch(`${BACKEND}/api/stream_transcription/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    credentials: 'include',
  })
  const data = await resp.json()
  if (!resp.ok || !data.success) throw new Error(data.error || data.message || 'Start failed')
  return data.task_id
}

export function connectTranscriptionSSE(taskId: string): EventSource {
  return new EventSource(`${BACKEND}/api/stream_transcription/${taskId}/events`, {
    withCredentials: true,
  })
}

export async function cancelTranscription(taskId: string): Promise<void> {
  const resp = await fetch(`${BACKEND}/api/stream_transcription/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId }),
    credentials: 'include',
  })
  const data = await resp.json()
  if (!resp.ok || !data.success) {
    throw new Error(data.error || data.message || 'Cancel failed')
  }
}
