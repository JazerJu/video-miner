// 章节API
import { getCSRFToken } from './GetCSRFToken'

export interface Chapter {
  id: string
  title: string
  startTime: number
  endTime?: number
  thumbnail?: string
  children?: Chapter[]
}

import { BACKEND } from '@/composables/ConfigAPI'

export class ChapterAPI {
  /**
   * 保存章节信息到后端
   */
  static async saveChapters(videoId: number, chapters: Chapter[]): Promise<boolean> {
    try {
      if (!videoId || videoId <= 0) {
        console.error('Invalid video ID:', videoId)
        return false
      }

      const csrfToken = await getCSRFToken()

      const response = await fetch(`${BACKEND}/api/videos/${videoId}/save_chapters`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ chapters }),
      })

      if (!response.ok) {
        console.error(`HTTP error! status: ${response.status}`)
        return false
      }

      const data = await response.json()

      if (data.success) {
        console.log('Chapters saved successfully:', data.chapters)
        return true
      } else {
        console.error('Failed to save chapters:', data.error)
        return false
      }
    } catch (error) {
      console.error('Error saving chapters:', error)
      return false
    }
  }

  /**
   * 从后端加载章节信息
   */
  static async loadChapters(videoId: number): Promise<Chapter[]> {
    try {
      if (!videoId || videoId <= 0) {
        console.error('Invalid video ID:', videoId)
        return []
      }

      const response = await fetch(`${BACKEND}/api/videos/${videoId}/load_chapters`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        console.error(`HTTP error! status: ${response.status}`)
        return []
      }

      const data = await response.json()

      if (data.success) {
        console.log('Chapters loaded successfully:', data.chapters)
        return data.chapters || []
      } else {
        console.error('Failed to load chapters:', data.error)
        return []
      }
    } catch (error) {
      console.error('Error loading chapters:', error)
      return []
    }
  }

  /**
   * 获取单个时间点的截图
   */
  static async getScreenshot(videoId: number, timestamp: number): Promise<string | null> {
    try {
      const csrfToken = await getCSRFToken()

      const response = await fetch(`${BACKEND}/api/videos/${videoId}/get_screenshot`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ timestamp }),
      })

      const data = await response.json()

      if (data.success) {
        console.log('Screenshot generated successfully:', data.screenshot)
        return `${BACKEND}${data.screenshot}`
      } else {
        console.error('Failed to generate screenshot:', data.error)
        return null
      }
    } catch (error) {
      console.error('Error generating screenshot:', error)
      return null
    }
  }

  /**
   * 批量获取章节截图
   */
  static async getChapterScreenshots(videoId: number, chapters: Chapter[]): Promise<Chapter[]> {
    try {
      const csrfToken = await getCSRFToken()

      const response = await fetch(`${BACKEND}/api/videos/${videoId}/get_screenshot`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ chapters }),
      })

      const data = await response.json()

      if (data.success && data.screenshots) {
        console.log('Chapter screenshots generated successfully:', data.screenshots)

        // 更新章节的缩略图URL
        const updatedChapters = chapters.map((chapter) => {
          const screenshot = data.screenshots.find(
            (s: any) => s.chapterId === chapter.id && !s.error,
          )
          if (screenshot) {
            const thumbnailUrl = `${BACKEND}${screenshot.screenshot}`
            console.log(`Setting thumbnail for chapter ${chapter.id}:`, thumbnailUrl)
            return {
              ...chapter,
              thumbnail: thumbnailUrl,
            }
          } else {
            console.log(`No screenshot found for chapter ${chapter.id}`)
          }
          return chapter
        })

        console.log('Updated chapters with thumbnails:', updatedChapters)
        return updatedChapters
      } else {
        console.error('Failed to generate chapter screenshots:', data.error)
        return chapters
      }
    } catch (error) {
      console.error('Error generating chapter screenshots:', error)
      return chapters
    }
  }
}
