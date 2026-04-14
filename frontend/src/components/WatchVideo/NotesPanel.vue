<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { markdownToHtml, processMarkdownContent } from '@/composables/ConvertMarkdown'
import { NotesAPI } from '@/composables/NotesAPI'
import { ElMessage } from '@/composables/useNotification'
import { useI18n } from 'vue-i18n'

import { BACKEND } from '@/composables/ConfigAPI'

// i18n functionality
const { t } = useI18n()

const props = defineProps({
  videoId: Number
})

const notesContent = ref('')
const editMode = ref(false)
const isLoading = ref(false)
const isSaving = ref(false)
const textareaRef = ref<HTMLTextAreaElement>()

// Image display configuration (keeping for potential future use)
const maxVisibleImages = ref(3)

// Character count and limit
const characterCount = computed(() => notesContent.value.length)
const characterLimit = 8000
const isOverLimit = computed(() => characterCount.value > characterLimit)

// Separate pure content from attachments
const parsedContent = computed(() => {
  const content = notesContent.value
  const imageRegex = /!\[([^\]]*)\]\(([^)]+)\)/g
  const attachments: Array<{ alt: string; url: string; markdown: string }> = []

  // Extract images
  let match
  while ((match = imageRegex.exec(content)) !== null) {
    let imageUrl = match[2]

    // If the URL is a relative path starting with /media/, prepend backend URL
    if (imageUrl.startsWith('/media/')) {
      imageUrl = `${BACKEND}${imageUrl}`
    }

    attachments.push({
      alt: match[1] || 'Image',
      url: imageUrl,
      markdown: match[0],
    })
  }

  // Remove image markdown from content, leaving pure text and code blocks
  const pureContent = content.replace(imageRegex, '').replace(/\n\n+/g, '\n\n').trim()

  return {
    pureContent,
    attachments,
  }
})

const renderedNotes = ref('')
const notesContentRef = ref<HTMLElement>()

// Render markdown content asynchronously
const renderMarkdown = async () => {
  const contentToRender = notesContent.value

  if (!contentToRender.trim()) {
    renderedNotes.value = ''
    return
  }

  try {
    const html = await markdownToHtml(contentToRender)
    renderedNotes.value = html
  } catch (error) {
    console.error('Failed to render markdown:', error)
    renderedNotes.value = `<p>${contentToRender}</p>`
  }
}

// Load notes when component mounts or videoId changes
const loadNotes = async () => {
  if (!props.videoId || props.videoId <= 0) {
    notesContent.value = ''
    return
  }

  isLoading.value = true
  try {
    const notes = await NotesAPI.loadNotes(props.videoId)
    notesContent.value = notes || ''
  } catch (error) {
    console.error('Failed to load notes:', error)
    ElMessage.error(t('loadNotesFailed'))
  } finally {
    isLoading.value = false
  }
}

const saveNotes = async () => {
  if (!props.videoId || props.videoId <= 0) {
    ElMessage.error('Invalid video ID')
    return
  }

  if (isOverLimit.value) {
    ElMessage.error(
      t('noteContentExceedsLimit', { current: characterCount.value, limit: characterLimit }),
    )
    return
  }

  isSaving.value = true
  try {
    await NotesAPI.saveNotes(props.videoId, notesContent.value)
    ElMessage.success(t('notesSavedSuccess'))
    editMode.value = false
  } catch (error: any) {
    console.error('Failed to save notes:', error)
    ElMessage.error(error.message || t('saveNotesFailed'))
  } finally {
    isSaving.value = false
  }
}

const toggleEdit = () => {
  if (editMode.value && characterCount.value > 0) {
    // Auto-save when exiting edit mode
    saveNotes()
  } else {
    editMode.value = !editMode.value
    if (editMode.value) {
      nextTick(() => {
        textareaRef.value?.focus()
      })
    }
  }
}

// Handle image paste (support multiple images)
const handlePaste = async (event: ClipboardEvent) => {
  const items = event.clipboardData?.items
  if (!items) return

  const imageFiles: File[] = []
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.type.indexOf('image') !== -1) {
      const file = item.getAsFile()
      if (file) imageFiles.push(file)
    }
  }

  if (imageFiles.length === 0) return

  event.preventDefault()
  await uploadImages(imageFiles)
}

// Unified image upload function (single image)
const uploadImage = async (file: File, defaultAlt: string = 'Uploaded Image') => {
  try {
    if (!props.videoId || props.videoId <= 0) {
      ElMessage.error('Invalid video ID')
      return
    }

    ElMessage.info('正在上传图片...')
    const imageUrl = await NotesAPI.uploadNoteImage(props.videoId, file)

    // Insert markdown image syntax at cursor position
    const textarea = textareaRef.value
    const imageMarkdown = `![${defaultAlt}](${imageUrl})`

    if (textarea && editMode.value) {
      const start = textarea.selectionStart
      const end = textarea.selectionEnd

      notesContent.value =
        notesContent.value.substring(0, start) + imageMarkdown + notesContent.value.substring(end)

      // Set cursor position after the inserted image
      nextTick(() => {
        const newPosition = start + imageMarkdown.length
        textarea.setSelectionRange(newPosition, newPosition)
        textarea.focus()
      })
    } else {
      // If not in edit mode or no textarea, append to end
      notesContent.value += (notesContent.value ? '\n\n' : '') + imageMarkdown
    }

    ElMessage.success('Image uploaded successfully')
  } catch (error: any) {
    console.error('Failed to upload image:', error)
    ElMessage.error(error.message || 'Image upload failed')
  }
}

// Batch image upload function (for album)
const uploadImages = async (files: File[]) => {
  const isUploading = ref(true)
  const uploadQueue = ref(files.length)
  const uploadError = ref<string | null>(null)

  try {
    ElMessage.info(`正在上传 ${files.length} 张图片...`)

    // Upload all images in parallel
    const uploadPromises = files.map((file) => {
      if (!props.videoId || props.videoId <= 0) {
        throw new Error('Invalid video ID')
      }
      return NotesAPI.uploadNoteImage(props.videoId, file)
    })

    const results = await Promise.allSettled(uploadPromises)
    const validResults: Array<{ filename: string; url: string }> = []
    const errors: string[] = []

    results.forEach((result, index) => {
      if (result.status === 'fulfilled' && result.value) {
        validResults.push({
          filename: files[index].name,
          url: result.value,
        })
      } else if (result.status === 'rejected') {
        errors.push(`${files[index].name}: ${result.reason?.message || 'Unknown error'}`)
      }
    })

    if (validResults.length === 0) {
      ElMessage.error(`Failed to upload ${errors.length} image(s): ${errors.join('; ')}`)
      return
    }

    if (errors.length > 0) {
      ElMessage.warning(`Uploaded ${validResults.length}/${files.length} images. Failed: ${errors.join('; ')}`)
    }

    // Insert markdown syntax
    const textarea = textareaRef.value
    let insertText = ''

    if (validResults.length > 1) {
      // Multiple images: create album block
      insertText = '\n```album\n'
      validResults.forEach((res) => {
        insertText += `![${res.filename}|auto](${res.url})\n`
      })
      insertText += '```\n'
    } else {
      // Single image: simple image markdown
      const res = validResults[0]
      insertText = `![${res.filename}](${res.url})`
    }

    if (textarea && editMode.value) {
      const start = textarea.selectionStart
      const end = textarea.selectionEnd

      notesContent.value = notesContent.value.substring(0, start) + insertText + notesContent.value.substring(end)

      // Set cursor position after the inserted content
      nextTick(() => {
        const newPosition = start + insertText.length
        textarea.setSelectionRange(newPosition, newPosition)
        textarea.focus()
      })
    } else {
      // If not in edit mode, append to end
      notesContent.value += (notesContent.value ? '\n\n' : '') + insertText
    }

    ElMessage.success(`Successfully uploaded ${validResults.length} image(s)`)
  } catch (error: any) {
    console.error('Failed to upload images:', error)
    ElMessage.error(error.message || 'Image upload failed')
  } finally {
    isUploading.value = false
    uploadQueue.value = 0
  }
}

// Image preview functionality
const openImagePreview = (initialIndex: number) => {
  const images = parsedContent.value.attachments
  if (!images.length) return

  let currentIndex = initialIndex

  // Create a modal/overlay for image preview
  const overlay = document.createElement('div')
  overlay.className =
    'fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm'

  const container = document.createElement('div')
  container.className = 'relative flex items-center justify-center w-full h-full'

  const img = document.createElement('img')
  img.className = 'max-w-[90vw] max-h-[90vh] rounded-lg shadow-2xl transition-opacity duration-300'

  const closeBtn = document.createElement('button')
  closeBtn.innerHTML = '✕'
  closeBtn.className =
    'absolute top-4 right-4 text-white text-2xl font-bold bg-black/50 rounded-full w-10 h-10 flex items-center justify-center hover:bg-black/70 transition-colors z-10'

  // Navigation arrows
  const leftArrow = document.createElement('button')
  leftArrow.innerHTML = '❮'
  leftArrow.className =
    'absolute left-4 top-1/2 transform -translate-y-1/2 text-white text-3xl font-bold bg-black/50 rounded-full w-12 h-12 flex items-center justify-center hover:bg-black/70 transition-colors z-10'

  const rightArrow = document.createElement('button')
  rightArrow.innerHTML = '❯'
  rightArrow.className =
    'absolute right-4 top-1/2 transform -translate-y-1/2 text-white text-3xl font-bold bg-black/50 rounded-full w-12 h-12 flex items-center justify-center hover:bg-black/70 transition-colors z-10'

  // Image counter
  const counter = document.createElement('div')
  counter.className =
    'absolute bottom-4 left-1/2 transform -translate-x-1/2 text-white bg-black/50 rounded-lg px-3 py-1 text-sm'

  const updateImage = () => {
    const currentImage = images[currentIndex]
    img.src = currentImage.url
    img.alt = currentImage.alt
    counter.textContent = `${currentIndex + 1} / ${images.length}`

    // Update arrow visibility
    leftArrow.style.display = images.length > 1 ? 'flex' : 'none'
    rightArrow.style.display = images.length > 1 ? 'flex' : 'none'
    leftArrow.style.opacity = currentIndex > 0 ? '1' : '0.5'
    rightArrow.style.opacity = currentIndex < images.length - 1 ? '1' : '0.5'
  }

  const goToPrevious = () => {
    if (currentIndex > 0) {
      currentIndex--
      updateImage()
    }
  }

  const goToNext = () => {
    if (currentIndex < images.length - 1) {
      currentIndex++
      updateImage()
    }
  }

  container.appendChild(img)
  container.appendChild(closeBtn)
  container.appendChild(leftArrow)
  container.appendChild(rightArrow)
  container.appendChild(counter)
  overlay.appendChild(container)
  document.body.appendChild(overlay)

  // Initialize with current image
  updateImage()

  const closeModal = () => {
    document.body.removeChild(overlay)
    document.removeEventListener('keydown', handleKeydown)
  }

  // Event listeners
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal()
  })

  closeBtn.addEventListener('click', closeModal)
  leftArrow.addEventListener('click', goToPrevious)
  rightArrow.addEventListener('click', goToNext)

  // Keyboard navigation
  const handleKeydown = (e: KeyboardEvent) => {
    e.preventDefault()
    switch (e.key) {
      case 'Escape':
        closeModal()
        break
      case 'ArrowLeft':
        goToPrevious()
        break
      case 'ArrowRight':
        goToNext()
        break
    }
  }
  document.addEventListener('keydown', handleKeydown)
}

// Auto-save functionality
let saveTimeout: ReturnType<typeof setTimeout>
const autoSave = () => {
  if (saveTimeout) clearTimeout(saveTimeout)
  saveTimeout = setTimeout(() => {
    if (editMode.value && notesContent.value.trim() && !isOverLimit.value) {
      saveNotes()
    }
  }, 30000) // Auto-save after 30 seconds of no typing
}

// --- Toolbar: Bold/Italic Toggle ---
const toggleBold = () => {
  const textarea = textareaRef.value
  if (!textarea) return

  const start = textarea.selectionStart
  const end = textarea.selectionEnd

  if (start === end) return // No selection

  const selectedText = notesContent.value.substring(start, end)
  const before = notesContent.value.substring(0, start)
  const after = notesContent.value.substring(end)

  // Check if already wrapped with **
  if (before.endsWith('**') && after.startsWith('**')) {
    // Remove the markers
    notesContent.value = before.slice(0, -2) + selectedText + after.slice(2)
    nextTick(() => {
      textarea.setSelectionRange(start - 2, end - 2)
      textarea.focus()
    })
  } else {
    // Add markers
    notesContent.value = before + '**' + selectedText + '**' + after
    nextTick(() => {
      textarea.setSelectionRange(start + 2, end + 2)
      textarea.focus()
    })
  }
}

const toggleItalic = () => {
  const textarea = textareaRef.value
  if (!textarea) return

  const start = textarea.selectionStart
  const end = textarea.selectionEnd

  if (start === end) return // No selection

  const selectedText = notesContent.value.substring(start, end)
  const before = notesContent.value.substring(0, start)
  const after = notesContent.value.substring(end)

  // Check if already wrapped with single * (not **)
  // Look for exactly one * before and after, not two
  if (before.endsWith('*') && !before.endsWith('**') && after.startsWith('*') && !after.startsWith('**')) {
    // Remove the markers
    notesContent.value = before.slice(0, -1) + selectedText + after.slice(1)
    nextTick(() => {
      textarea.setSelectionRange(start - 1, end - 1)
      textarea.focus()
    })
  } else {
    // Add markers (but don't conflict with existing bold)
    // If the selection already has **, we should not wrap with *
    if (selectedText.includes('**')) return

    notesContent.value = before + '*' + selectedText + '*' + after
    nextTick(() => {
      textarea.setSelectionRange(start + 1, end + 1)
      textarea.focus()
    })
  }
}

// --- Toolbar: Image Layout Toggle ---
const setImageLayout = (layout: 'grid' | 'carousel' | 'thumbnail') => {
  const textarea = textareaRef.value
  if (!textarea) return

  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const selectedText = notesContent.value.substring(start, end)

  if (!selectedText.trim()) {
    ElMessage.warning('请先选择图片行')
    return
  }

  // Regex to match existing album block: ```album[ mode]?\n...\n```
  const albumBlockRegex = /^(\s*)```album(\s+(\w+))?\n([\s\S]*?)\n(\s*)```(\s*)$/
  const match = selectedText.match(albumBlockRegex)

  if (match) {
    // Case B: Selection is already an album block
    const [, leadingSpaces, , currentMode, imageLines, trailingSpaces] = match
    const existingMode = currentMode || 'grid'

    if (existingMode === layout) {
      // Same mode clicked: unwrap (remove album markers)
      const unwrapped = imageLines
      notesContent.value =
        notesContent.value.substring(0, start) + unwrapped + notesContent.value.substring(end)
      nextTick(() => {
        textarea.setSelectionRange(start, start + unwrapped.length)
        textarea.focus()
      })
    } else {
      // Different mode: switch mode
      const newMode = layout === 'grid' ? '' : ` ${layout}`
      const wrapped = `${leadingSpaces}\`\`\`album${newMode}\n${imageLines}\n${trailingSpaces}\`\`\`${trailingSpaces ? '\n' : ''}`
      notesContent.value =
        notesContent.value.substring(0, start) + wrapped + notesContent.value.substring(end)
      nextTick(() => {
        textarea.setSelectionRange(start, start + wrapped.length)
        textarea.focus()
      })
    }
  } else {
    // Case A: Selection contains bare image lines (not wrapped)
    // Check if there are any image markdown lines
    const imageLineRegex = /^!\[.*?\]\(.*?\)$/
    const lines = selectedText.split('\n')
    const imageLines = lines.filter(line => imageLineRegex.test(line.trim()))

    if (imageLines.length === 0) {
      ElMessage.warning('选中的内容中没有图片')
      return
    }

    // Wrap with album block
    const mode = layout === 'grid' ? '' : ` ${layout}`
    const wrapped = `\`\`\`album${mode}\n${imageLines.join('\n')}\n\`\`\`\n`
    notesContent.value =
      notesContent.value.substring(0, start) + wrapped + notesContent.value.substring(end)
    nextTick(() => {
      textarea.setSelectionRange(start, start + wrapped.length)
      textarea.focus()
    })
  }
}

// Check current active layout for selected text
const getActiveLayout = (): 'grid' | 'carousel' | 'thumbnail' | null => {
  const textarea = textareaRef.value
  if (!textarea) return null

  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const selectedText = notesContent.value.substring(start, end)

  const albumBlockRegex = /^(\s*)```album(\s+(\w+))?\n([\s\S]*?)\n(\s*)```(\s*)$/
  const match = selectedText.match(albumBlockRegex)

  if (match) {
    const currentMode = match[3] || 'grid'
    if (currentMode === 'carousel') return 'carousel'
    if (currentMode === 'thumbnail') return 'thumbnail'
    return 'grid'
  }

  return null
}

const activeLayout = computed(() => getActiveLayout())

// Watch for content changes to re-render markdown and auto-save
watch(() => notesContent.value, async () => {
  await renderMarkdown()
  autoSave()
})

// Watch for rendered content changes to process mermaid
watch([renderedNotes, editMode], async ([newNotes, newMode], [oldNotes, oldMode]) => {
  // Only process when not in edit mode (view mode)
  if (!newMode) {
    await nextTick()
    // Additional delay to ensure DOM is fully rendered after v-if/v-else transition
    await new Promise(resolve => setTimeout(resolve, 50))
    if (notesContentRef.value) {
      await processMarkdownContent(notesContentRef.value)
    }
  }
})

onMounted(async () => {
  await loadNotes()
  await renderMarkdown()
})

// Watch for videoId changes
watch(
  () => props.videoId,
  async () => {
    await loadNotes()
    await renderMarkdown()
  },
  { immediate: false },
)
</script>

<template>
  <div class="p-6 relative">
    <!-- Header -->
    <div class="flex justify-between items-center mb-6">
      <div class="flex items-center space-x-2">
        <div
          v-if="isLoading"
          class="animate-spin w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full"
        ></div>
      </div>

      <div class="flex items-center space-x-4">
        <!-- Character count -->
        <div
          class="text-sm px-3 py-1 rounded-lg bg-slate-700/50 border border-slate-600/30"
          :class="isOverLimit ? 'text-red-400 border-red-500/50' : 'text-slate-300'"
        >
          {{ characterCount }} / {{ characterLimit }}
        </div>

        <!-- Edit/Save button -->
        <button
          @click="toggleEdit"
          :disabled="isSaving || isLoading"
          class="px-4 py-2 text-sm rounded-lg transition-all duration-200 font-medium"
          :class="[
            editMode
              ? 'bg-blue-600/80 hover:bg-blue-600 text-white border border-blue-500/30 disabled:opacity-50'
              : 'bg-slate-700/50 hover:bg-slate-600/70 text-slate-300 border border-slate-600/30'
          ]"
        >
          <span v-if="isSaving" class="flex items-center">
            <svg
              class="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                class="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="4"
              ></circle>
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            保存中...
          </span>
          <span v-else>{{ editMode ? '保存' : '编辑' }}</span>
        </button>
      </div>
    </div>

    <!-- Content -->
    <div>
      <div v-if="isLoading" class="flex items-center justify-center py-12 text-slate-400">
        <div
          class="animate-spin w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full mr-3"
        ></div>
        {{ t('loadingNotes') }}
      </div>

      <!-- Edit Mode -->
      <div v-else-if="editMode" class="space-y-4">
        <div class="relative">
          <textarea
            ref="textareaRef"
            v-model="notesContent"
            @paste="handlePaste"
            class="w-full h-80 p-4 bg-slate-700/30 border rounded-xl resize-none focus:outline-none focus:ring-2 text-white placeholder-slate-400 backdrop-blur-sm transition-all notes-textarea"
            :class="[
              isOverLimit
                ? 'border-red-500/50 focus:ring-red-500/50'
                : 'border-slate-600/50 focus:ring-blue-500/50'
            ]"
            :placeholder="t('notePlaceholder')"
          ></textarea>
        </div>

        <!-- Toolbar -->
        <div class="bg-slate-700/40 border border-slate-600/30 rounded-lg p-1.5 flex items-center">
          <!-- Bold -->
          <button
            @click="toggleBold"
            title="粗体 (Bold)"
            class="p-1.5 rounded hover:bg-slate-600/50 text-slate-400 hover:text-white transition-colors"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M15.6 10.79c.97-.67 1.65-1.77 1.65-2.79 0-2.26-1.75-4-4-4H7v14h7.04c2.09 0 3.71-1.7 3.71-3.79 0-1.52-.86-2.82-2.15-3.42zM10 6.5h3c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-3v-3zm3.5 9H10v-3h3.5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5z"/>
            </svg>
          </button>

          <!-- Italic -->
          <button
            @click="toggleItalic"
            title="斜体 (Italic)"
            class="p-1.5 rounded hover:bg-slate-600/50 text-slate-400 hover:text-white transition-colors"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M10 4v3h2.21l-3.42 8H6v3h8v-3h-2.21l3.42-8H18V4z"/>
            </svg>
          </button>

          <!-- Separator -->
          <div class="w-px h-5 bg-slate-600/50 mx-1"></div>

          <!-- Grid Layout -->
          <button
            @click="setImageLayout('grid')"
            title="网格布局 (Grid)"
            class="p-1.5 rounded hover:bg-slate-600/50 transition-colors"
            :class="activeLayout === 'grid' ? 'text-blue-400 bg-slate-600/50' : 'text-slate-400 hover:text-white'"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M4 4h4v4H4V4zm6 0h4v4h-4V4zm6 0h4v4h-4V4zM4 10h4v4H4v-4zm6 0h4v4h-4v-4zm6 0h4v4h-4v-4zM4 16h4v4H4v-4zm6 0h4v4h-4v-4zm6 0h4v4h-4v-4z"/>
            </svg>
          </button>

          <!-- Carousel Layout -->
          <button
            @click="setImageLayout('carousel')"
            title="轮播布局 (Carousel)"
            class="p-1.5 rounded hover:bg-slate-600/50 transition-colors"
            :class="activeLayout === 'carousel' ? 'text-blue-400 bg-slate-600/50' : 'text-slate-400 hover:text-white'"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h16v2H4v-2z"/>
            </svg>
          </button>

          <!-- Thumbnail Layout -->
          <button
            @click="setImageLayout('thumbnail')"
            title="缩略图布局 (Thumbnail)"
            class="p-1.5 rounded hover:bg-slate-600/50 transition-colors"
            :class="activeLayout === 'thumbnail' ? 'text-blue-400 bg-slate-600/50' : 'text-slate-400 hover:text-white'"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M4 4h10v10H4V4zm12 0h4v10h-4V4zM4 16h10v4H4v-4zm12 0h4v4h-4v-4z"/>
            </svg>
          </button>
        </div>

        <!-- Help text -->
        <div
          class="text-xs text-slate-300 bg-slate-700/30 p-3 rounded-lg border border-slate-600/30"
        >
          <strong class="text-blue-400">快速帮助：</strong>
          支持完整 Markdown 语法 | 粘贴多张图片自动创建相册 | 自动保存（30秒后）
        </div>

        <!-- Warning for character limit -->
        <div
          v-if="isOverLimit"
          class="text-sm text-red-300 bg-red-900/20 p-3 rounded-lg border border-red-500/30"
        >
          ⚠️ 内容超出字符限制，请删减至 {{ characterLimit }} 字符以内
        </div>
      </div>

      <!-- View Mode -->
      <div v-else>
        <div v-if="notesContent.trim()" class="space-y-6">
          <!-- Pure Notes Content -->
          <div
            v-if="renderedNotes.trim()"
            ref="notesContentRef"
            class="prose prose-sm max-w-none prose-invert notes-content bg-slate-800/30 rounded-xl p-4 backdrop-blur-lg border border-slate-600/30"
            v-html="renderedNotes"
          ></div>
        </div>

        <!-- Empty State -->
        <div v-else class="text-center py-16 text-slate-400">
          <svg
            class="mx-auto h-16 w-16 text-slate-500 mb-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.5"
              d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
            ></path>
          </svg>
          <p class="text-xl font-medium text-slate-300 mb-2">{{ t('noNotes') }}</p>
          <p class="text-sm text-slate-500">{{ t('clickEditToStartNotes') }}</p>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.notes-textarea {
  color: white !important;
}

/* Main prose styles - using Tailwind prose plugin */
:deep(.notes-content) {
  color: #e2e8f0 !important;
}

:deep(.notes-content h1),
:deep(.notes-content h2),
:deep(.notes-content h3),
:deep(.notes-content h4),
:deep(.notes-content h5),
:deep(.notes-content h6) {
  color: white !important;
  font-weight: bold;
  border-bottom: 1px solid #334155;
  padding-bottom: 0.3em;
  margin-bottom: 0.5em;
  margin-top: 1em;
}

:deep(.notes-content h1) {
  font-size: 2em;
}

:deep(.notes-content h2) {
  font-size: 1.5em;
}

:deep(.notes-content h3) {
  font-size: 1.25em;
}

:deep(.notes-content p) {
  color: rgb(226 232 240) !important;
  margin-bottom: 1em;
  line-height: 1.6;
}

:deep(.notes-content ul),
:deep(.notes-content ol) {
  padding-left: 1.5em;
  margin-bottom: 1em;
}

:deep(.notes-content ul) {
  list-style-type: disc;
}

:deep(.notes-content ol) {
  list-style-type: decimal;
}

:deep(.notes-content li) {
  color: rgb(226 232 240) !important;
  margin-bottom: 0.25em;
}

:deep(.notes-content strong),
:deep(.notes-content b) {
  color: white !important;
  font-weight: bold;
}

:deep(.notes-content code) {
  background-color: #1e293b !important;
  color: rgb(96 165 250) !important;
  padding: 0.2em 0.4em;
  border-radius: 0.25rem;
  font-family: monospace;
}

:deep(.notes-content pre) {
  background-color: #1e293b !important;
  padding: 1em;
  border-radius: 0.5rem;
  overflow-x: auto;
  margin-bottom: 1em;
}

:deep(.notes-content pre code) {
  background-color: transparent !important;
  padding: 0;
  color: inherit !important;
}

:deep(.notes-content blockquote) {
  border-left: 4px solid #3b82f6;
  padding-left: 1em;
  color: rgb(148 163 184);
  font-style: italic;
  margin-bottom: 1em;
}

:deep(.notes-content a) {
  color: rgb(96 165 250) !important;
  text-decoration: underline;
}

/* Mermaid styles */
:deep(.notes-content .mermaid) {
  background-color: #1e293b;
  padding: 1rem;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
  display: flex;
  justify-content: center;
}

:deep(.notes-content .mermaid svg) {
  max-width: 100%;
  height: auto;
}

/* Album: Grid Mode (Default) */
:deep(.notes-content .album-grid) {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  margin: 1.5rem 0;
  padding: 1rem;
  background-color: #1e293b;
  border-radius: 0.5rem;
  border: 1px solid #334155;
}

:deep(.notes-content .album-item) {
  display: flex;
  flex-direction: column;
  justify-content: center;
  break-inside: avoid;
  background-color: #0f172a;
  border-radius: 0.5rem;
  overflow: hidden;
  transition: transform 0.2s;
}

:deep(.notes-content .album-item:hover) {
  transform: translateY(-2px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
}

:deep(.notes-content .album-item img) {
  width: 100%;
  height: auto;
  object-fit: cover;
  margin: 0 !important;
  border-radius: 0 !important;
}

:deep(.notes-content .album-caption) {
  padding: 0.5rem;
  font-size: 0.85rem;
  color: rgb(148 163 184);
  text-align: center;
  background-color: #0f172a;
  border-top: 1px solid #1e293b;
}

/* Album: Carousel & Thumbnail Modes */
:deep(.notes-content .album-carousel-container) {
  position: relative;
  background-color: #1e293b;
  border-radius: 0.5rem;
  border: 1px solid #334155;
  padding: 1rem;
  margin: 1.5rem 0;
  user-select: none;
}

:deep(.notes-content .carousel-stage) {
  position: relative;
  width: 100%;
  height: 400px;
  background-color: #0f172a;
  border-radius: 0.5rem;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

:deep(.notes-content .carousel-slide) {
  display: none;
  width: 100%;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

:deep(.notes-content .carousel-slide.active) {
  display: flex;
}

:deep(.notes-content .carousel-slide img) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  margin: 0 !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}

/* Floating Caption in Carousel */
:deep(.notes-content .carousel-caption-overlay) {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent);
  color: white;
  padding: 2rem 1rem 1rem;
  text-align: center;
  font-size: 0.9rem;
  opacity: 0;
  transition: opacity 0.3s;
}

:deep(.notes-content .carousel-stage:hover .carousel-caption-overlay) {
  opacity: 1;
}

/* Navigation Arrows */
:deep(.notes-content .carousel-nav-btn) {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(0, 0, 0, 0.5);
  color: white;
  border: none;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  transition: background 0.2s;
  z-index: 10;
}

:deep(.notes-content .carousel-nav-btn:hover) {
  background: rgba(59, 130, 246, 0.8);
}

:deep(.notes-content .carousel-prev) {
  left: 1rem;
}

:deep(.notes-content .carousel-next) {
  right: 1rem;
}

/* Thumbnail Strip */
:deep(.notes-content .carousel-thumbs) {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}

:deep(.notes-content .carousel-thumb-item) {
  width: 60px;
  height: 60px;
  flex-shrink: 0;
  border-radius: 0.25rem;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  opacity: 0.6;
  transition: all 0.2s;
}

:deep(.notes-content .carousel-thumb-item img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
  margin: 0 !important;
  border-radius: 0 !important;
}

:deep(.notes-content .carousel-thumb-item:hover) {
  opacity: 1;
}

:deep(.notes-content .carousel-thumb-item.active) {
  border-color: rgb(96 165 250);
  opacity: 1;
}

:deep(.notes-content .image-figure) {
  margin: 1rem 0;
  display: inline-block;
}

:deep(.notes-content .image-caption) {
  text-align: center;
  color: rgb(148 163 184);
  font-size: 0.85rem;
  margin-top: 0.5rem;
}
</style>