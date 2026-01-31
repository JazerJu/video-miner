// Type definitions for media-related data structures

export interface Category {
  id: number
  name: string
  items: MediaItem[] | Null
}

export interface Video {
  id: number
  name: string
  thumbnail: string
  url: string
  length: string
  last_modified: string
  description: string
  tags?: string[]
  type: 'video' // Type discriminator for union types
}

export interface Collection {
  id: number
  name: string
  videos: Video[]
  type: 'collection' // Type discriminator for union types
  thumbnail: string
  cover?: string
  last_modified: string
}

export type MediaItem = Video | Collection // Union type for folder display

export interface VideoInfoData {
  id: number
  name: string
  url: string
  description: string
  thumbnailUrl: string
  videoLength: string
  lastModified: string
  rawLang?: string // raw_lang from backend ('en', 'zh', 'jp')
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
  collectionCount: number
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
