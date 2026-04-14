// 笔记API
import { getCSRFToken } from './GetCSRFToken'
import { markVideoDirty } from './useVideoDirtyState'

import { BACKEND } from '@/composables/ConfigAPI'

export class NotesAPI {
  /**
   * 保存笔记到后端
   */
  static async saveNotes(videoId: number, notes: string): Promise<boolean> {
    try {
      if (!videoId || videoId <= 0) {
        console.error('Invalid video ID:', videoId)
        return false
      }

      // Validate notes length (8000 characters max)
      if (notes.length > 8000) {
        throw new Error('Notes exceed maximum length of 8000 characters')
      }

      const csrfToken = await getCSRFToken()

      const response = await fetch(`${BACKEND}/api/videos/${videoId}/save_notes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify({ notes }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`)
      }

      const data = await response.json()

      if (data.success) {
        console.log('Notes saved successfully')
        markVideoDirty(videoId)
        return true
      } else {
        throw new Error(data.error || 'Failed to save notes')
      }
    } catch (error) {
      console.error('Error saving notes:', error)
      throw error
    }
  }

  /**
   * 从后端加载笔记
   */
  static async loadNotes(videoId: number): Promise<string> {
    try {
      if (!videoId || videoId <= 0) {
        console.error('Invalid video ID:', videoId)
        return ''
      }

      const response = await fetch(`${BACKEND}/api/videos/${videoId}/load_notes`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        console.error(`HTTP error! status: ${response.status}`)
        return ''
      }

      const data = await response.json()

      if (data.success) {
        console.log('Notes loaded successfully')
        return data.notes || ''
      } else {
        console.error('Failed to load notes:', data.error)
        return ''
      }
    } catch (error) {
      console.error('Error loading notes:', error)
      return ''
    }
  }

  /**
   * 上传笔记中的图片 (使用新的VideoAttachment系统)
   */
  static async uploadNoteImage(videoId: number, imageFile: File): Promise<string> {
    try {
      if (!videoId || videoId <= 0) {
        throw new Error('Invalid video ID')
      }

      // Validate file type
      const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
      if (!allowedTypes.includes(imageFile.type)) {
        throw new Error('Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed.')
      }

      // Validate file size (e.g., 10MB max)
      const maxSize = 10 * 1024 * 1024 // 10MB
      if (imageFile.size > maxSize) {
        throw new Error('File size too large. Maximum size is 10MB.')
      }

      const csrfToken = await getCSRFToken()

      const formData = new FormData()
      formData.append('image', imageFile)

      const response = await fetch(`${BACKEND}/api/videos/${videoId}/upload_note_image`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`)
      }

      const data = await response.json()

      if (data.success) {
        console.log('Image uploaded successfully:', data.imageUrl)
        return data.imageUrl // Now returns full URL from backend
      } else {
        throw new Error(data.error || 'Failed to upload image')
      }
    } catch (error) {
      console.error('Error uploading image:', error)
      throw error
    }
  }

  /**
   * 通用附件上传 (支持notes)
   */
  static async uploadAttachment(
    videoId: number,
    imageFile: File,
    contextType: 'notes' = 'notes',
    contextId: string = '',
    altText: string = '',
  ): Promise<{
    id: number
    url: string
    filename: string
    originalName: string
    fileType: string
    fileSize: number
    contextType: string
    contextId: string
    altText: string
    uploadTime: string
  }> {
    try {
      if (!videoId || videoId <= 0) {
        throw new Error('Invalid video ID')
      }

      // Validate file type
      const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
      if (!allowedTypes.includes(imageFile.type)) {
        throw new Error('Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed.')
      }

      // Validate file size (10MB max)
      const maxSize = 10 * 1024 * 1024 // 10MB
      if (imageFile.size > maxSize) {
        throw new Error('File size too large. Maximum size is 10MB.')
      }

      const csrfToken = await getCSRFToken()

      const formData = new FormData()
      formData.append('image', imageFile)
      formData.append('context_type', contextType)
      formData.append('context_id', contextId)
      formData.append('alt_text', altText || imageFile.name)

      const response = await fetch(`${BACKEND}/api/videos/${videoId}/upload_attachment`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`)
      }

      const data = await response.json()

      if (data.success) {
        console.log('Attachment uploaded successfully:', data.attachment)
        return data.attachment
      } else {
        throw new Error(data.error || 'Failed to upload attachment')
      }
    } catch (error) {
      console.error('Error uploading attachment:', error)
      throw error
    }
  }

  /**
   * 获取视频的所有附件
   */
  static async listAttachments(
    videoId: number,
    contextType?: 'notes',
  ): Promise<
    Array<{
      id: number
      url: string
      filename: string
      originalName: string
      fileType: string
      fileSize: number
      contextType: string
      contextId: string
      altText: string
      uploadTime: string
    }>
  > {
    try {
      if (!videoId || videoId <= 0) {
        throw new Error('Invalid video ID')
      }

      let url = `${BACKEND}/api/videos/${videoId}/list_attachments`
      if (contextType) {
        url += `?context_type=${contextType}`
      }

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`)
      }

      const data = await response.json()

      if (data.success) {
        return data.attachments || []
      } else {
        throw new Error(data.error || 'Failed to list attachments')
      }
    } catch (error) {
      console.error('Error listing attachments:', error)
      throw error
    }
  }
}
