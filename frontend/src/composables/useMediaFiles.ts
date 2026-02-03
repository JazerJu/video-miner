import { BACKEND } from '@/composables/ConfigAPI'

export function useMediaFiles() {
  const checkDubbingFile = async (originalSrc: string, lang: string): Promise<boolean> => {
    if (!originalSrc) return false
    
    const match = originalSrc.match(/\/([^\/]+)\.mp4$/)
    if (!match) return false
    
    const md5 = match[1]
    const dubbedUrl = originalSrc.replace(`${md5}.mp4`, `${md5}_${lang}.mp4`)
    
    try {
      const res = await fetch(dubbedUrl, { method: 'HEAD' })
      return res.ok
    } catch (e) {
      console.warn(`Failed to check dubbing file: ${dubbedUrl}`, e)
      return false
    }
  }

  const checkSubtitleExistence = async (id: number, lang: string): Promise<boolean> => {
    if (!id || id <= 0) return false
    
    try {
      const res = await fetch(`${BACKEND}/api/subtitle/query/${id}?lang=${encodeURIComponent(lang)}`, {
        credentials: 'include',
      })
      return res.ok
    } catch (e) {
      return false
    }
  }

  return {
    checkDubbingFile,
    checkSubtitleExistence
  }
}
