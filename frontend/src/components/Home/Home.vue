<!-- 主要布局组件，复杂业务逻辑 -->
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { defineExpose, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { FolderOpen, Radio } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useNotification } from '@/composables/useNotification'
import Sidebar from '@/components/Home/Sidebar.vue'
import VideoDisplayToggler from '@/components/VideoDisplayToggler.vue'
import VideoCard from '@/components/Home/VideoCard.vue'
import BatchMoveDialog from '@/components/dialogs/BatchMoveDialog.vue'

import BatchToolbar from '@/components/Home/BatchToolbar.vue'
import { getCSRFToken, getCookie } from '@/composables/GetCSRFToken'
import TasksView from '@/components/Home/TasksView.vue'
import type { Video, Category, RequestVideo } from '@/types/media'
import StreamMediaCard from '@/components/Home/StreamMediaCard.vue'
import EnhancedSubtitleDialog from '@/components/dialogs/EnhancedSubtitleDialog.vue'
import SettingsPanel from '@/components/Home/SettingsPanel.vue'
import LibraryView from '@/components/Home/LibraryView.vue'
import ThumbnailDialog from '@/components/dialogs/ThumbnailDialog.vue'
import RealtimeTranscriptionDialog from '@/components/dialogs/RealtimeTranscriptionDialog.vue'
import { useThumbnail } from '@/composables/thumbnail'
import { useHiddenCategories } from '@/composables/useHiddenCategories'

import { useRouter } from 'vue-router'
import { consumeDirtyVideos, hasDirtyVideos } from '@/composables/useVideoDirtyState'

const router = useRouter()

/*
  说明：Home.vue 顶层页面（Layout）
*/

/** 通用 DELETE 请求封装 */
async function requestDelete(url: string, okMsg = '操作成功'): Promise<boolean> {
  try {
    const resp = await fetch(url, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
    })
    const data = await resp.json()

    if (!resp.ok || data?.success === false) throw new Error(data?.message || resp.statusText)

    successNotify(data?.message || t(okMsg) || okMsg)
    return true
  } catch (e: any) {
    console.error(e)
    errorNotify(e.message || t('requestFailed'))
    return false
  }
}

// Hidden categories functionality
const { filterCategories, updateHiddenCategories, refreshHiddenCategories } = useHiddenCategories()

async function onCategoriesUpdated() {
  // Refresh hidden categories from backend API and update filtering
  try {
    await refreshHiddenCategories()
  } catch (error) {
    console.error('Failed to refresh hidden categories:', error)
    // Fallback to localStorage for unauthenticated users
    const newHiddenCategories = JSON.parse(localStorage.getItem('vidgo_hidden_categories') || '[]')
    updateHiddenCategories(newHiddenCategories)
  }
}

// 1.更新侧边栏选中菜单序号-->更新main page内容
const currentMenuIdx = ref(0)
const activeSettingsTab = ref('model')
const filterMode = ref<'folders' | 'tags'>('folders')

function updateMenuIndex(idx: number) {
  currentMenuIdx.value = idx
  resetPagination() // 切换视图时重置分页
  // console.log('Sidebar Menu updated to:', idx)

  if (idx === 0) {
    // 首页
    currentCategory.value = null
    // console.log(currentCategory)
  } else if (idx === 1) {
    //媒体库
    currentCategory.value = null // not inside any folder
  } else if (idx === 2) {
    // Settings
    currentCategory.value = null
  }

  if ((idx === 0 || idx === 1) && hasDirtyVideos()) {
    fetchVideoData()
  }
}

function updateSettingsTab(tab: string) {
    activeSettingsTab.value = tab
}

// 1.1 打开搜索框
const libraryViewRef = ref<InstanceType<typeof LibraryView> | null>(null)
function handleOpenSearch() {
  updateMenuIndex(1)
  nextTick(() => {
    libraryViewRef.value?.focusSearch()
  })
}

// 1.2 打开设置 - Now switches to menu index 3
function handleOpenSettings() {
  updateMenuIndex(3)
}

// 1.2.侧边栏定义分类的函数，展示对应分类的Items
const categories = ref<Category[]>([])
defineExpose({ categories })

const currentCategory = ref<Category | null>(null)
const currentCategoryItems = ref<Video[]>([])

const handleSelectCategory = (id: number) => {
  const cat = categories.value.find((c) => Number(c.id) === id) ?? null
  currentCategoryItems.value = cat ? cat.items : []
  currentCategory.value = cat
  currentMenuIdx.value = -1
  resetPagination() // 切换分类时重置分页
}

// 2.2. 上传 本地视频/音频
// File upload is handled by StreamMediaCard component

// 2.3. VideoCard中的视频操作

// 为单个视频打开字幕操作对话框
function generateSubtitle(video: Video): void {
  // Set the selected video for the dialog
  selectedIds.value = [video.id]
  showSubtitleDialog.value = true
}

/** 删除视频，并在所有本地 state 中同步移除 */
async function deleteVideo(video: Video) {
  // 二次确认
  try {
    await ElMessageBox.confirm(
      `${t('deleteConfirm')}「${video.name || '该视频'}」吗？`,
      t('deletePrompt'),
      {
        type: 'warning',
      },
    )
  } catch {
    return // 用户点击取消
  }

  // 调后端
  const ok = await requestDelete(`${BACKEND}/api/videos/${video.id}/delete`, t('videoDeleted'))
  if (!ok) return

  // 本地同步移除
  const remove = (arr: Video[]) => arr.filter((v) => v.id !== video.id)

  Object.keys(videoData.value).forEach(
    (key) => (videoData.value[key] = remove(videoData.value[key])),
  )
}
// 2.4 批量操作
const selectedIds = ref<number[]>([]) // 被勾选的视频 id 列表

// 使用computed来确保批量模式始终与selectedIds同步
const isBatchMode = computed(() => selectedIds.value.length > 0)

// 分页功能
const itemsPerPage = 20
const currentPage = ref(1)

// 重置分页到第一页的函数
function resetPagination() {
  currentPage.value = 1
}
async function batchDelete() {
  if (!selectedIds.value.length) {
    warningNotify(t('selectVideosToDelete'))
    return
  }

  try {
    await ElMessageBox.confirm(
      t('confirmDeleteText', { count: selectedIds.value.length }),
      t('confirmDeleteTitle'),
      {
        confirmButtonText: t('confirmDeleteBtn'),
        cancelButtonText: t('cancel'),
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return // 用户取消删除
  }

  try {
    const csrfToken = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/batch_action`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      credentials: 'include',
      body: JSON.stringify({
        action: 'delete',
        videoIds: selectedIds.value,
      }),
    })

    const result = await response.json()

    if (result.success) {
      successNotify(result.message || t('deleteSuccess'))

      // 清空选择并刷新数据
      selectedIds.value = []
      await fetchVideoData()
      await nextTick() // Ensure DOM updates
    } else {
      errorNotify(result.message || t('deleteFailed'))
      if (result.errors && result.errors.length > 0) {
        console.error('删除错误详情：', result.errors)
      }
    }
  } catch (error) {
    console.error('批量删除视频失败：', error)
    errorNotify(t('networkError'))
  }
}
function batchSubtitle() {
  if (!selectedIds.value.length) {
    warningNotify(t('selectVideoFirst'))
    return
  }

  showSubtitleDialog.value = true
}

/** 批量合并视频 */
async function batchConcat() {
  if (!selectedIds.value.length) {
    warningNotify(t('selectVideoFirst'))
    return
  }

  // Get selected videos with their details
  const selectedVideos: Video[] = selectedIds.value
    .map((id) => videoIndex.value[id])
    .filter(Boolean)
    .sort((a, b) => {
      // Sort by the order they appear in selectedIds
      return selectedIds.value.indexOf(a.id) - selectedIds.value.indexOf(b.id)
    })

  if (selectedVideos.length !== selectedIds.value.length) {
    errorNotify('部分选中的视频信息缺失，请重试')
    return
  }

  // Build sequence display message
  const sequenceInfo = selectedVideos
    .map((video, index) => `(${index + 1}-${video.name}-${video.length})`)
    .join('\n')

  // Show confirmation dialog with video sequence and warnings
  try {
    await ElMessageBox.confirm(
      `视频合并序列：<br>${sequenceInfo.replace(/\n/g, '<br>')}<br><br>⚠️ 重要提示：<br>• 原视频文件将被删除<br>• 如果所有视频的字幕语言相同且视频分辨率、编码相同，系统将：<br>&nbsp;&nbsp;- 自动合并相同语言的字幕文件<br>&nbsp;&nbsp;- 调整第二个及后续视频的字幕时间戳<br>&nbsp;&nbsp;- 创建新的合并视频文件<br><br>确定要继续合并吗？`,
      '视频合并确认',
      {
        confirmButtonText: '确定合并',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: true,
        customStyle: {
          width: '600px',
        },
      },
    )
  } catch {
    return // User cancelled
  }

  try {
    const csrfToken = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/batch_action`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      credentials: 'include',
      body: JSON.stringify({
        action: 'concat',
        videoIds: selectedIds.value,
      }),
    })
    const result = await response.json()
    if (result.success) {
      successNotify(result.message || '合并请求已提交')
      selectedIds.value = []
      fetchVideoData()
    } else {
      errorNotify(result.message || '合并失败')
    }
  } catch (error) {
    console.error('批量合并视频失败：', error)
    errorNotify('网络错误，请重试')
  }
}
const showBatchMoveDialog = ref(false)
const showRealtimeTranscriptionDialog = ref(false)

async function onBatchMoved() {
  const ids = [...selectedIds.value] // 1️⃣ 复制一份待删列表
  selectedIds.value = [] // 清空勾选，让批量栏立即消失

  // 2️⃣ 本地把视频从所有分类 / 合集中移除
  categories.value.forEach((cat) => {
    cat.items = cat.items.filter((it: Video) => !(it.type === 'video' && ids.includes(it.id)))
  })
  // 触发顶层数组更新（有时不需要，但保险起见）
  categories.value = [...categories.value]

  await nextTick() // 3️⃣ DOM 立刻重渲染，视频瞬间消失

  // 4️⃣ 后台真正执行批量移动 / 删除
  //    不必等待 UI；如果想捕获错误可以 try/catch
  fetchVideoData()
}

const showSubtitleDialog = ref(false)

// Thumbnail functionality
const {
  showThumbnailDialog,
  thumbnailTarget,
  onEditThumbnail,
  handleThumbnailUpdated: composableHandleThumbnailUpdated,
} = useThumbnail()

// id → Video 对象的索引表,方便 O(1) 查询
// const videoIndex = computed<Record<number, Video>>(() => {
//   const m: Record<number, Video> = {}
//   Object.values(videoData.value)
//     .flat()
//     .forEach((v) => (m[v.id] = v))
//   return m
// })
const videoIndex = computed<Record<number, Video>>(() => {
  const map: Record<number, Video> = {}

  // 把所有分类里的视频放入索引
  Object.values(videoData.value)
    .flat()
    .forEach((v) => {
      map[v.id] = v as Video
    })

  return map
})

/** 当前勾选的视频对象数组 */
const selectedVideos = computed<Video[]>(() =>
  selectedIds.value.map((id) => videoIndex.value[id]).filter(Boolean),
)

// 过滤后的分类（用于隐藏分类功能）
const filteredCategories = computed(() => {
  return filterCategories(categories.value)
})

// 所有视频的集合，用于媒体库
const allVideos = computed<Video[]>(() => {
  return Object.values(videoData.value).flat()
})

const filteredMediaGroups = computed(() => {
  if (filterMode.value === 'folders') {
    return filteredCategories.value
  } else {
    // Group by Tags
    const map = new Map<string, Video[]>()
    // 'Uncategorized' for videos with no tags
    const noTagVideos: Video[] = []

    // Iterate all videos
    Object.values(videoData.value).flat().forEach(video => {
        // Backend tags might be JSON string or array, handled by Video interface as string[]
        // Ensure tags is array
        const tags = Array.isArray(video.tags) ? video.tags : []
        
        if (tags.length === 0) {
            noTagVideos.push(video)
        } else {
            tags.forEach(tag => {
                if (!map.has(tag)) map.set(tag, [])
                map.get(tag)!.push(video)
            })
        }
    })

    const result: Category[] = []
    map.forEach((videos, tag) => {
        result.push({ id: -1, name: tag, items: videos }) // ID -1 for transient tag groups
    })
    
    // Sort by tag name
    result.sort((a, b) => a.name.localeCompare(b.name))

    if (noTagVideos.length > 0) {
        result.push({ id: -1, name: t('uncategorized') || 'Uncategorized', items: noTagVideos })
    }
    return result
  }
})



// 分页计算属性 - 仅用于分类视图和合集视图
const paginatedCurrentCategory = computed(() => {
  if (!currentCategory.value?.items) return null

  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  const items = currentCategory.value.items.slice(start, end)

  return {
    ...currentCategory.value,
    items,
  }
})

const totalCategoryPages = computed(() => {
  if (!currentCategory.value?.items) return 1
  return Math.ceil(currentCategory.value.items.length / itemsPerPage)
})

function onSubtitleSubmitted() {
  // 后端成功 → 关闭弹窗 + 清空勾选
  showSubtitleDialog.value = false
  selectedIds.value = []
}

async function handleThumbnailUpdated() {
  console.log('handleThumbnailUpdated!!')
  await fetchVideoData()
  // Force Vue reactivity by triggering array change
  if (currentCategory.value) {
    currentCategory.value = categories.value.find((c) => c.id === currentCategory.value!.id) ?? null
  }
  await nextTick() // Ensure DOM updates
}

// Handle video rename
async function handleVideoRenamed(video: Video, newName: string) {
  // Update local data immediately for better UX
  video.name = newName //也是如此，因为VideoCard的Key没有改变，系统不自动更改VideoCard的内容
  // Refresh data from server to ensure consistency
  await fetchVideoData() // 以后节省流量可以不调用
  await nextTick() // Ensure DOM updates
}



// 3.获取分类/视频信息
// 获取分类信息
const videoData = ref<Record<string, Video[]>>({}) // raw map: { category → list }
import axios from 'axios'
async function fetchCategories() {
  const { data } = await axios.get(`${BACKEND}/api/category/query/0`)
  categories.value = data.categories
}
// 获取视频信息
async function fetchVideoData() {
  try {
    // 获取隐藏的分类ID列表
    const { hiddenCategoryIds } = useHiddenCategories()
    // console.log('Hidden category IDs:', hiddenCategoryIds.value)
    const hiddenCategoriesParam =
      hiddenCategoryIds.value.length > 0
        ? `?hidden_categories=${hiddenCategoryIds.value.join(',')}`
        : ''
    // console.log('Fetching with URL:', `${BACKEND}/api/videos${hiddenCategoriesParam}`)

    const res = await fetch(`${BACKEND}/api/videos${hiddenCategoriesParam}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    // 后端返回 { data: [...] }
    const jsonResponse = await res.json()
    // console.log('Full API response:', jsonResponse)
    const { data: catArray = [] } = jsonResponse
    
    // ➜ 关键：把 id 为 null 的那一条也映射成 Category
    // console.log('Category array:', catArray)
    
    // Simplification: Direct mapping, assuming backend returns { loose_videos: [...] } structure correctly
    // Since we removed Collections, everything should be in loose_videos or similar
    // We map backend response to Frontend Category structure
    categories.value = catArray.map((cat: any) => {
        const categoryName = cat.name || '未归档'
        return {
            id: cat.id ?? 0,
            name: categoryName,
            items: (cat.loose_videos ?? []).map((v: any) => ({
                ...v,
                thumbnail: v.thumbnail_url || v.thumbnail || '',
                length: v.video_length || v.length || '',
                description: v.description || '',
                rawLang: v.raw_lang || v.rawLang || '',
                videoSource: v.video_source || v.videoSource || '',
                sourceUrl: v.source_url || v.sourceUrl || '',
                type: 'video',
                categoryName: categoryName,  // 添加分类名称到每个视频
                categoryId: cat.id ?? 0      // 添加分类ID到每个视频
            }))
        }
    })

    // Update videoData for easy access
    videoData.value = {}
    categories.value.forEach((cat) => {
      videoData.value[cat.name] = cat.items as Video[]
    })

    consumeDirtyVideos()
  } catch (err) {
    console.error(err)
  }
}
import { BACKEND } from '@/composables/ConfigAPI'

// Track authentication state
const isAuthenticated = ref(false)
const currentUser = ref(null)

// i18n functionality
const { t } = useI18n()
const { success: successNotify, error: errorNotify, warning: warningNotify } = useNotification()

// Check if user is authenticated before fetching
async function checkAuthAndFetch() {
  try {
    const response = await fetch(`${BACKEND}/api/auth/profile/`, {
      credentials: 'include',
    })

    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        // User is authenticated, fetch data
        isAuthenticated.value = true
        currentUser.value = data.user
        fetchVideoData()
      } else {
        // Not authenticated - redirect to login
        isAuthenticated.value = false
        currentUser.value = null
        router.push('/login')
      }
    } else {
      // Not authenticated - redirect to login
      isAuthenticated.value = false
      currentUser.value = null
      router.push('/login')
    }
  } catch (error) {
    console.error('Error checking auth status:', error)
    // On error, redirect to login
    isAuthenticated.value = false
    currentUser.value = null
    router.push('/login')
  }
}

// Check if root user exists
const checkRootExists = async () => {
  try {
    const response = await fetch(`${BACKEND}/api/auth/check-root/`)
    const data = await response.json()
    return data.root_exists
  } catch (error) {
    console.error('Error checking root status:', error)
    return false
  }
}



// Handle user area click from Sidebar
const handleUserAreaClick = async () => {
  if (currentUser.value) {
    // User is already logged in, Sidebar will handle dropdown
    return
  } else {
    router.push('/login')
  }
}

onMounted(() => {
  // Reset browser tab title to default
  document.title = 'VidGo'
  checkAuthAndFetch()
  window.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
})

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.ctrlKey && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    handleOpenSearch()
  }
}
</script>

<template>
  <div class="flex h-screen overflow-hidden">
    <!-- Sidebar on the left -->
    <Sidebar
      :categories="isAuthenticated ? filteredCategories : []"
      :currentMenuIdx="currentMenuIdx"
      :activeSettingsTab="activeSettingsTab"
      :isAuthenticated="isAuthenticated"
      @update-menuIndex="updateMenuIndex"
      @open-settings="handleOpenSettings"
      @refresh="checkAuthAndFetch"
      @show-login="handleUserAreaClick"
      @update-settings-tab="updateSettingsTab"
    />
    <!-- 右侧可Y轴滚动内容区 -->
    <main
      class="flex-1 h-full p-6 overflow-y-auto bg-gradient-to-br from-gray-900 via-slate-800 to-blue-900"
    >
      <template v-if="currentMenuIdx === 0">
        <div class="p-6">
          <h1 class="text-2xl font-bold mb-3 text-white">{{ t('videoManagementSystem') }}</h1>
          <StreamMediaCard @upload-complete="fetchVideoData" />
          <!-- 功能卡片组 - 只保留流式转录并居中 -->
          <div class="flex justify-center mt-8 space-x-8">
            <!-- 流式转录卡片 -->
            <div
              class="feature-card-hover bg-gradient-to-br from-gray-800/80 via-slate-700/80 to-blue-800/80 backdrop-blur-md rounded-2xl p-8 cursor-pointer border border-white/30 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105 max-w-xs text-center"
              @click="router.push('/stream-transcription')"
            >
              <div
                class="w-16 h-16 mx-auto rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 bg-opacity-20 flex items-center justify-center mb-4"
              >
                <Radio :size="32" class="text-blue-400" />
              </div>
              <h3 class="text-xl font-semibold text-white mb-1">
                {{ t('liveRecordTranscription') }}
              </h3>
              <p class="text-white/70 text-sm leading-relaxed">
                {{ t('liveRecordTranscriptionDesc') }}
              </p>
            </div>
          </div>
          <!-- File upload is handled by StreamMediaCard component -->

          <TasksView />
        </div>
      </template>

      <!-- 📌 Settings -->
      <template v-if="currentMenuIdx === 3">
          <div class="h-full p-6">
            <SettingsPanel 
                :active-tab="activeSettingsTab"
                :categories="categories"
                @categories-updated="onCategoriesUpdated"
            />
          </div>
      </template>

      <!-- 📌 媒体库 -->
      <template v-if="currentMenuIdx === 1">
        <!-- 新的媒体库视图，带完整筛选和排序功能 -->
        <LibraryView
          ref="libraryViewRef"
          :videos="allVideos"
          :batch-mode="isBatchMode"
          v-model:selected-ids="selectedIds"
          @generate-subtitle="generateSubtitle"
          @delete="deleteVideo"
          @edit-thumbnail="onEditThumbnail"
          @rename-video="handleVideoRenamed"
          @show-move-dialog="showBatchMoveDialog = true"
          @generate-subtitles="batchSubtitle"
          @delete-videos="batchDelete"
          @videos-updated="fetchVideoData"
        />
      </template>



      <!-- 📌 单一分类 -->
      <template v-else-if="currentMenuIdx === -1 && currentCategory">
        <h2 class="text-3xl font-bold mb-4 text-white">{{ currentCategory.name }}</h2>

        <BatchToolbar
          :batch-mode="isBatchMode"
          :selected-ids="selectedIds"
          @show-move-dialog="showBatchMoveDialog = true"

          @generate-subtitles="batchSubtitle"
          @delete-videos="batchDelete"
          @concat-videos="batchConcat"
        />

        <MediaItemCards
          v-if="paginatedCurrentCategory"
          :category="paginatedCurrentCategory"
          view="grid"
          :batch-mode="isBatchMode"
          v-model:selected-ids="selectedIds"
          @generate-subtitle="generateSubtitle"
          @delete="deleteVideo"
          @edit-thumbnail="onEditThumbnail"

        />

        <!-- 分页组件 -->
        <div v-if="totalCategoryPages > 1" class="flex justify-center mt-6">
          <el-pagination
            v-model:current-page="currentPage"
            :total="currentCategory.items.length"
            :page-size="itemsPerPage"
            layout="prev, pager, next"
            :pager-count="7"
            class="pagination-custom"
          />
        </div>
      </template>
    </main>
    <!-- Upload progress panel is handled by StreamMediaCard component -->
    <!-- Dialog -->
    <ThumbnailDialog
      v-model="showThumbnailDialog"
      :target="thumbnailTarget"
      @target-updated="handleThumbnailUpdated"
    />

    <BatchMoveDialog
      v-model="showBatchMoveDialog"
      :selected-ids="selectedIds"
      :categories="categories.map((c) => ({ id: c.id, name: c.name }))"
      @moved="onBatchMoved"
    />



    <EnhancedSubtitleDialog
      v-model="showSubtitleDialog"
      :video-id-list="selectedIds"
      :video-name-list="selectedVideos.map((v) => v.name)"
      @submitted="onSubtitleSubmitted"
    />

    <!-- 实时转录对话框 -->
    <RealtimeTranscriptionDialog
      v-model="showRealtimeTranscriptionDialog"
    />
  </div>
</template>

<style scoped>
/* 基础圆点 */
.status-dot {
  display: inline-block;
  width: 10px; /* 圆点直径 */
  height: 10px;
  border-radius: 50%;
  background-color: var(--el-color-info); /* 未完成：灰蓝色 */
}

/* 分页样式 */
:deep(.pagination-custom .el-pagination) {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
}

:deep(.pagination-custom .el-pager li) {
  min-width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #6b7280;
  background: transparent;
  border: none;
}

:deep(.pagination-custom .el-pager li:hover) {
  background-color: #f3f4f6;
  color: #374151;
}

:deep(.pagination-custom .el-pager li.is-active) {
  background-color: #10b981;
  color: white;
}

:deep(.pagination-custom .btn-prev),
:deep(.pagination-custom .btn-next) {
  min-width: 36px;
  height: 36px;
  border-radius: 8px;
  background: transparent;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #6b7280;
}

:deep(.pagination-custom .btn-prev:hover),
:deep(.pagination-custom .btn-next:hover) {
  background-color: #f3f4f6;
  color: #374151;
}

:deep(.pagination-custom .btn-prev:disabled),
:deep(.pagination-custom .btn-next:disabled) {
  cursor: not-allowed;
  opacity: 0.5;
}

/* 完成状态 */
.status-dot.done {
  background-color: var(--el-color-success); /* 完成：绿色 */
}
</style>
