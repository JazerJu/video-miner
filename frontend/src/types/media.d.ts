// Type definitions for media-related data structures

export interface Category {
  id: number
  name: string
  items: Video[] | Null
}

export interface Video {
  id: number
  name: string
  thumbnail: string  // 缩略图文件名
  thumbnail_url?: string  // 后端返回的完整缩略图字段
  url: string
  length: string
  video_length_seconds?: number
  file_size?: number
  file_created_time?: string
  last_modified: string
  description: string
  tags?: string[]
  type: 'video' // Type discriminator for union types
  categoryId?: number | null
  categoryName?: string | null
  rawLang?: string
  videoSource?: string
  sourceUrl?: string
}

export interface VideoInfoData {
  id: number
  name: string
  url: string
  description: string
  thumbnailUrl: string
  videoLength: string
  lastModified: string
  rawLang?: string // raw_lang from backend ('en', 'zh', 'jp')
  last_played_time?: number
}

// Task Items
export interface SubtitleTaskRow {
  videoName: string
  status: 'Processing' | 'Completed' | 'Waiting' | 'Error'
  progress: number
  result: string
}

export interface DownloadTaskRow {
  videoName: string
  status: 'Processing' | 'Completed' | 'Waiting' | 'Error'
  progress: number
  result: string
}

// Task row items
export interface RequestVideo {
  bvid: string
  url: string
  title: string
  thumbnail: string
  duration: number
  owner: string
  /** List of all video parts/episodes */
  video_data: VideoPart[]
}

/** Information for a single video part/episode */
export interface VideoPart {
  cid: number
  page: number
  part: string
  duration: number
  // Additional fields like first_frame/dimension can be added as needed
}
