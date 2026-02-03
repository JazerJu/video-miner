import { getCSRFToken } from '@/composables/GetCSRFToken'
import { BACKEND } from './ConfigAPI'

export interface Tag {
  id: number
  name: string
  color: string
  created_time?: string
}

export async function loadTags(): Promise<Tag[]> {
  try {
    const response = await fetch(`${BACKEND}/api/tags/`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
    })
    const result = await response.json()
    if (result.success) {
      return result.tags || []
    }
    return []
  } catch (error) {
    console.error('Error loading tags:', error)
    return []
  }
}

export async function createTag(name: string, color: string = '#3B82F6'): Promise<Tag | null> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/tags/create`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({ name, color }),
    })
    const result = await response.json()
    if (result.success) {
      return result.tag
    }
    throw new Error(result.error || 'Failed to create tag')
  } catch (error) {
    console.error('Error creating tag:', error)
    throw error
  }
}

export async function updateTag(tagId: number, name?: string, color?: string): Promise<Tag | null> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/tags/${tagId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({ name, color }),
    })
    const result = await response.json()
    if (result.success) {
      return result.tag
    }
    throw new Error(result.error || 'Failed to update tag')
  } catch (error) {
    console.error('Error updating tag:', error)
    throw error
  }
}

export async function deleteTag(tagId: number): Promise<void> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/tags/${tagId}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
    })
    const result = await response.json()
    if (!result.success) {
      throw new Error(result.error || 'Failed to delete tag')
    }
  } catch (error) {
    console.error('Error deleting tag:', error)
    throw error
  }
}

export async function batchDeleteTags(tagIds: number[]): Promise<number> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/tags/batch_delete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({ tag_ids: tagIds }),
    })
    const result = await response.json()
    if (result.success) {
      return result.deleted_count || 0
    }
    throw new Error(result.error || 'Failed to batch delete tags')
  } catch (error) {
    console.error('Error batch deleting tags:', error)
    throw error
  }
}

export async function mergeTags(sourceTagId: number, targetTagId: number): Promise<number> {
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/tags/merge`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({ source_tag_id: sourceTagId, target_tag_id: targetTagId }),
    })
    const result = await response.json()
    if (result.success) {
      return result.updated_count || 0
    }
    throw new Error(result.error || 'Failed to merge tags')
  } catch (error) {
    console.error('Error merging tags:', error)
    throw error
  }
}
