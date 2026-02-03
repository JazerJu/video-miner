import { BACKEND } from './ConfigAPI'
import type { Video } from '@/types/media'

export interface SimilarVideoResponse {
  id: number
  name: string
  url: string
  thumbnail_url: string
  video_length: string
}

export async function getSimilarVideos(videoId: number): Promise<SimilarVideoResponse[]> {
  const response = await fetch(`${BACKEND}/api/videos/${videoId}/similar`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch similar videos: ${response.status}`)
  }

  const data = await response.json()

  if (data.success && data.videos) {
    return data.videos
  }

  return []
}
