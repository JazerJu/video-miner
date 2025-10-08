<!-- 主要布局组件，复杂业务逻辑 -->
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { defineExpose, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Microphone, Upload } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import Sidebar from '@/components/Home/Sidebar.vue'
import SearchModal from '@/components/Home/SearchModal.vue'
import VideoDisplayToggler from '@/components/VideoDisplayToggler.vue'
import VideoCard from '@/components/Home/VideoCard.vue'
import BatchMoveDialog from '@/components/dialogs/BatchMoveDialog.vue'
import BatchMoveToCollectionDialog from '@/components/dialogs/BatchMoveToCollectionDialog.vue'
import BatchToolbar from '@/components/Home/BatchToolbar.vue'
import MediaItemCards from '@/components/Home/MediaItemCards.vue'
import { getCSRFToken, getCookie } from '@/composables/GetCSRFToken'
import TasksView from '@/components/Home/TasksView.vue'
import type { MediaItem, Video, Collection, Category, RequestVideo } from '@/types/media'
import StreamMediaCard from '@/components/Home/StreamMediaCard.vue'
import EnhancedSubtitleDialog from '@/components/dialogs/EnhancedSubtitleDialog.vue' // ← 新增
import SettingsDialog from '@/components/dialogs/SettingsDialog.vue'
import ThumbnailDialog from '@/components/dialogs/ThumbnailDialog.vue' // ← 新增
import RealtimeTranscriptionDialog from '@/components/dialogs/RealtimeTranscriptionDialog.vue' // ← 新增实时转录对话框
import { useThumbnail } from '@/composables/thumbnail'
import { useHiddenCategories } from '@/composables/useHiddenCategories'
import { HistoryAPI } from '@/composables/HistoryAPI'
/*
  说明：Home.vue 顶层页面（Layout）

  ──────────────────────────────────────────────────────
  ◇ 布局结构
    • 左侧 <Sidebar>：负责导航菜单 + 分类（Folder）列表。
    • 右侧 Main：根据当前菜单 / 所选文件夹渲染不同内容。

  ──────────────────────────────────────────────────────
  ◇ 页面切换逻辑
    1. Home（currentMenu = 0）
       - 视频管理首页
       - 支持「输入外链 → 解析预览卡片 → 下载视频」流程
       - 三个功能卡片：本地媒体上传 / 文本转语音 / 实时录音转写
       - <TasksView> 展示字幕等后台任务进度
    2. Library（currentMenu = 1）
       - 展示所有视频（不含合集），支持批量模式
    3. Folder Content
       - 当在 Sidebar 选中文件夹时进入
       - 仅渲染该文件夹下的 MediaItem 列表
       - 支持批量移动分类 / 生成字幕 / 删除 / 编辑缩略图

  ──────────────────────────────────────────────────────
  ◇ 主要功能点
    • fetchCategories       —— 拉取分类：填充 categories（Sidebar）与 右侧Main page内容.
    • fetchVideoData        —— 拉取所有视频： 拉取分类->collection->视频的三级json，更新 categories.items
    • submitUrl             —— POST /stream_media/query，生成外链视频预览卡片
    • handleFileChange      —— 本地视频 / 音频上传到后端
    • generateSubtitle      —— 将视频加入字幕队列（POST + CSRF）
    • deleteVideo           —— 删除视频（DELETE；同步前端列表）
    • handleSelectCategory  —— 侧边栏文件夹点击：切页并加载对应 items
    • Batch 操作            —— 进入批量选择，移动分类 / 批量字幕
    • getCookie             —— 简易读取 csrftoken，供所有带凭证请求使用

  ──────────────────────────────────────────────────────
  ◇ 组件协作
    • <Sidebar>
        - 发事件：update:currentMenu / open-search / select-folder / refresh
    • <SearchModal>
        - v-model 控制显示
    • <MediaItemCards>
        - 根据 view="grid" 渲染视频卡片/Collection 卡片
        - 向父触发：edit-thumbnail / generate-subtitle / delete / category-moved
    • <BatchMoveDialog>
        - 处理批量移动分类
    • <TasksView>
        - 轮询并展示后台任务状态

  ──────────────────────────────────────────────────────
  ◇ 状态管理（ref / computed）
    • categories            —— Sidebar 分类数组
    • categories         —— 带 items 的分类完整结构
    • allVideos          —— 扁平化的视频列表（Library 用）
    • currentMenu        —— 侧边导航索引
    • currentPage        —— 'main' | 'library' | 'folder_content'
    • currentCategory      —— 选中的文件夹对象
    • currentCategoryItems —— 当前文件夹下的 MediaItem 列表
    • selectedIds        —— 批量模式下勾选的视频 ID
    • isBatchMode        —— 是否处于批量选择状态（computed）
    • requestVideo       —— 外链解析后的预览数据
    • showSearchModal    —— 搜索弹窗开关
    • showBatchMoveDialog—— 批量移动弹窗开关

  ──────────────────────────────────────────────────────
  ◇ 外部依赖
    • Element Plus 组件 & 图标
    • TailwindCSS 工具类
    • axios / fetch API
    • 后端环境变量 VITE_BACKEND_ORIGIN
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

    ElMessage.success(data?.message || t(okMsg) || okMsg)
    return true
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e.message || t('requestFailed'))
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
    // History页面
    currentCategory.value = null
    fetchRecentVideos() // 获取最近视频数据
  }
}
// 1.1 打开搜索框
const showSearchModal = ref(false)
function handleOpenSearch() {
  showSearchModal.value = true
}

// 1.2 打开设置对话框
const showSettingsDialog = ref(false)
function handleOpenSettings() {
  showSettingsDialog.value = true
}

// 1.2.侧边栏定义分类的函数，展示对应分类的Items
const categories = ref<Category[]>([])
defineExpose({ categories })

const currentCategory = ref<Category | null>(null)
const currentCategoryItems = ref<MediaItem[]>([])

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
    ElMessage.warning(t('selectVideosToDelete'))
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
      ElMessage.success(result.message || t('deleteSuccess'))

      // 清空选择并刷新数据
      selectedIds.value = []
      await fetchVideoData()
      await nextTick() // Ensure DOM updates
    } else {
      ElMessage.error(result.message || t('deleteFailed'))
      if (result.errors && result.errors.length > 0) {
        console.error('删除错误详情：', result.errors)
      }
    }
  } catch (error) {
    console.error('批量删除视频失败：', error)
    ElMessage.error(t('networkError'))
  }
}
function batchSubtitle() {
  ElMessage.success(`生成字幕：${selectedIds.value.join(', ')}`)
  // 打开弹窗
  if (!selectedIds.value.length) {
    ElMessage.warning(t('selectVideoFirst'))
    return
  }
  showSubtitleDialog.value = true
}

/** 批量合并视频 */
async function batchConcat() {
  if (!selectedIds.value.length) {
    ElMessage.warning(t('selectVideoFirst'))
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
    ElMessage.error('部分选中的视频信息缺失，请重试')
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
      ElMessage.success(result.message || '合并请求已提交')
      selectedIds.value = []
      fetchVideoData()
    } else {
      ElMessage.error(result.message || '合并失败')
    }
  } catch (error) {
    console.error('批量合并视频失败：', error)
    ElMessage.error('网络错误，请重试')
  }
}
const showBatchMoveDialog = ref(false)
const showBatchMoveToCollectionDialog = ref(false)
const showRealtimeTranscriptionDialog = ref(false)

function handleOpenRealtimeTranscription() {
  showRealtimeTranscriptionDialog.value = true
}
async function onBatchMoved() {
  const ids = [...selectedIds.value] // 1️⃣ 复制一份待删列表
  selectedIds.value = [] // 清空勾选，让批量栏立即消失

  // 2️⃣ 本地把视频从所有分类 / 合集中移除
  categories.value.forEach((cat) => {
    cat.items = cat.items.filter((it: Video) => !(it.type === 'video' && ids.includes(it.id)))
  })
  // 如果你在 Collection 详情页，需要同步当前集合
  if (currentCollection.value) {
    currentCollection.value.videos = currentCollection.value.videos.filter(
      (v) => !ids.includes(v.id),
    )
  }
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

  // ① 把分类里的"散装"视频（即无Collection）放进来
  Object.values(videoData.value)
    .flat()
    .forEach((v) => {
      map[v.id] = v as Video
    })

  // ② 额外把各个 Collection 的内部视频也放进来
  collectionMap.value.forEach((col) => {
    col.videos?.forEach((v) => (map[v.id] = v))
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

// History页面 - 通过API获取最近50个视频
const recentVideos = ref<Video[]>([])
const isLoadingHistory = ref(false)
const historyError = ref('')

// 获取最近视频数据
const fetchRecentVideos = async () => {
  isLoadingHistory.value = true
  historyError.value = ''

  try {
    const videos = await HistoryAPI.getRecentVideos()
    recentVideos.value = videos
  } catch (error: any) {
    console.error('Failed to fetch recent videos:', error)
    historyError.value = error.message || '获取最近视频失败'
  } finally {
    isLoadingHistory.value = false
  }
}

// History页面的分页
const paginatedRecentVideos = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  // Sort videos by name using natural sorting like PlayList
  const sortedVideos = recentVideos.value.sort((a, b) => {
    return a.name.localeCompare(b.name, undefined, {
      numeric: true,
      sensitivity: 'base',
    })
  })
  return sortedVideos.slice(start, end)
})

const totalHistoryPages = computed(() => {
  return Math.ceil(recentVideos.value.length / itemsPerPage)
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

const paginatedCollectionVideos = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  // Sort videos by name using natural sorting like PlayList
  const sortedVideos = currentCollectionVideos.value.sort((a, b) => {
    return a.name.localeCompare(b.name, undefined, {
      numeric: true,
      sensitivity: 'base',
    })
  })
  return sortedVideos.slice(start, end)
})

const totalCollectionPages = computed(() => {
  return Math.ceil(currentCollectionVideos.value.length / itemsPerPage)
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
  if (currentCollection.value) {
    currentCollection.value = collectionMap.value.get(currentCollection.value.id) ?? null
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

// Handle collection moved - instant UI update by removing from current category
async function handleCollectionMoved(movedCollection: Collection) {
  console.log('handleCollectionMoved called with:', movedCollection)
  // Remove collection from all categories immediately for instant UI feedback
  categories.value.forEach((category) => {
    category.items = category.items.filter(
      (item: MediaItem) => !(item.type === 'collection' && item.id === movedCollection.id),
    )
  })

  // Update current category items if we're viewing a specific category
  if (currentCategory.value) {
    currentCategory.value.items = currentCategory.value.items.filter(
      (item: MediaItem) => !(item.type === 'collection' && item.id === movedCollection.id),
    )
  }
  console.log('Current category after filtering:', currentCategory.value)
  // Force reactivity update
  await nextTick()
  await fetchVideoData()
}

// 2.4.点击CollectionCard，展示该Collection中的所有视频
const currentCollection = ref<Collection | null>(null)
const collectionMap = ref<Map<number, Collection>>(new Map())
const currentCollectionVideos = computed(() => currentCollection.value?.videos ?? [])
const openCollection = (id: number) => {
  // console.log(id, 'collection opened!!')
  const col = collectionMap.value.get(id)
  if (!col) return

  currentCollection.value = col
  currentMenuIdx.value = 10 // 约定 10 = Collection 详情
  selectedIds.value = [] // 清批量选择
  resetPagination() // 切换合集时重置分页
}

// 添加返回函数，正确处理从Collection返回到来源分类
const returnFromCollection = () => {
  if (currentCategory.value) {
    // 如果来自某个分类，返回到该分类
    currentMenuIdx.value = -1
  } else {
    // 如果来自媒体库，返回到媒体库
    currentMenuIdx.value = 1
  }
  currentCollection.value = null
  resetPagination()
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
    console.log('Hidden category IDs:', hiddenCategoryIds.value)
    const hiddenCategoriesParam =
      hiddenCategoryIds.value.length > 0
        ? `?hidden_categories=${hiddenCategoryIds.value.join(',')}`
        : ''
    console.log('Fetching with URL:', `${BACKEND}/api/videos${hiddenCategoriesParam}`)

    const res = await fetch(`${BACKEND}/api/videos${hiddenCategoriesParam}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    // 后端返回 { data: [...] }
    const jsonResponse = await res.json()
    console.log('Full API response:', jsonResponse)
    const { data: catArray = [] } = jsonResponse
    // ➜ 关键：把 id 为 null 的那一条也映射成 Category
    console.log('Category array:', catArray)
    categories.value = catArray.map((cat: any) => {
      console.log(
        'Processing category:',
        cat.name,
        'Collections:',
        cat.collections?.length ?? 0,
        'Loose videos:',
        cat.loose_videos?.length ?? 0,
      )
      return {
        id: cat.id ?? 0,
        name: cat.name || '未归档',
        items: [
          ...(cat.collections ?? []).map((c: any) => ({
            ...c,
            type: 'collection',
            cover: c.thumbnail || '',
          })),
          ...(cat.loose_videos ?? []).map((v: any) => ({
            ...v,
            type: 'video',
          })),
        ],
      }
    })
    console.log(categories)
    // 获取Collection Maps
    collectionMap.value.clear()
    categories.value.forEach((cat) => {
      cat.items?.forEach((it: MediaItem) => {
        if (it.type === 'collection') {
          collectionMap.value.set(it.id, it as Collection)
        }
      })
    })
    videoData.value = {}
    categories.value.forEach((cat) => {
      videoData.value[cat.name] = cat.items.filter((it: MediaItem) => it.type === 'video')
    })
  } catch (err) {
    console.error(err)
  }
}
import { BACKEND } from '@/composables/ConfigAPI'

// Track authentication state
const isAuthenticated = ref(false)
const currentUser = ref(null)

// Login/Register dialog states
const showLoginDialog = ref(false)
const showRegisterDialog = ref(false)

// Login form
const loginForm = ref({
  username: '',
  password: '',
})

// Registration form
const registerForm = ref({
  username: '',
  password: '',
  email: '',
})

// i18n functionality
const { t } = useI18n()

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
        // Not authenticated
        isAuthenticated.value = false
        currentUser.value = null
      }
    } else {
      // Not authenticated
      isAuthenticated.value = false
      currentUser.value = null
    }
  } catch (error) {
    console.error('Error checking auth status:', error)
    // On error, assume not authenticated
    isAuthenticated.value = false
    currentUser.value = null
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

// Login function
const handleLogin = async () => {
  if (!loginForm.value.username || !loginForm.value.password) {
    ElMessage.error('请输入用户名和密码')
    return
  }

  try {
    const response = await fetch(`${BACKEND}/api/auth/login/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(loginForm.value),
    })

    const data = await response.json()

    if (data.success) {
      currentUser.value = data.user
      isAuthenticated.value = true
      showLoginDialog.value = false
      loginForm.value = { username: '', password: '' }
      ElMessage.success('登录成功')
      // Refresh data after login
      checkAuthAndFetch()
    } else {
      ElMessage.error(data.error || '登录失败')
    }
  } catch (error) {
    console.error('Login error:', error)
    ElMessage.error('网络错误，请重试')
  }
}

// Register root user
const handleRegister = async () => {
  if (!registerForm.value.username || !registerForm.value.password) {
    ElMessage.error('请输入用户名和密码')
    return
  }

  try {
    const response = await fetch(`${BACKEND}/api/auth/register-root/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(registerForm.value),
    })

    const data = await response.json()

    if (data.success) {
      currentUser.value = data.user
      isAuthenticated.value = true
      showRegisterDialog.value = false
      registerForm.value = { username: '', password: '', email: '' }
      ElMessage.success('根用户创建成功')
      // Refresh data after registration
      checkAuthAndFetch()
    } else {
      ElMessage.error(data.error || '注册失败')
    }
  } catch (error) {
    console.error('Register error:', error)
    ElMessage.error('网络错误，请重试')
  }
}

// Handle user area click from Sidebar
const handleUserAreaClick = async () => {
  if (currentUser.value) {
    // User is already logged in, Sidebar will handle dropdown
    return
  } else {
    // Check if root exists
    const rootExists = await checkRootExists()
    if (rootExists) {
      showLoginDialog.value = true
    } else {
      showRegisterDialog.value = true
    }
  }
}

onMounted(() => {
  // Reset browser tab title to default
  document.title = 'VidGo'
  checkAuthAndFetch()
})
</script>

<template>
  <div class="flex h-screen overflow-hidden">
    <!-- Sidebar on the left -->
    <Sidebar
      :categories="isAuthenticated ? filteredCategories : []"
      :currentMenuIdx="currentMenuIdx"
      :isAuthenticated="isAuthenticated"
      @update-menuIndex="updateMenuIndex"
      @open-search="handleOpenSearch"
      @open-settings="handleOpenSettings"
      @select-category="handleSelectCategory"
      @refresh="checkAuthAndFetch"
      @show-login="handleUserAreaClick"
    />

    <!-- 搜索Modal -->
    <SearchModal v-model:visible="showSearchModal" @close="showSearchModal = false" />
    <!-- 右侧可Y轴滚动内容区 -->
    <main
      class="flex-1 h-full p-6 overflow-y-auto bg-gradient-to-br from-gray-900 via-slate-800 to-blue-900"
    >
      <template v-if="currentMenuIdx === 0">
        <div class="p-6">
          <h1 class="text-2xl font-bold mb-3 text-white">{{ t('videoManagementSystem') }}</h1>
          <StreamMediaCard @upload-complete="fetchVideoData" />
          <!-- 功能卡片组 - 只保留录音转写并居中 -->
          <div class="flex justify-center mt-8 space-x-8">
            <!-- 录音转写卡片 -->
            <div
              class="feature-card-hover bg-gradient-to-br from-gray-800/80 via-slate-700/80 to-blue-800/80 backdrop-blur-md rounded-2xl p-8 cursor-pointer border border-white/30 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105 max-w-xs text-center"
              @click="handleOpenRealtimeTranscription"
            >
              <div
                class="w-16 h-16 mx-auto rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 bg-opacity-20 flex items-center justify-center mb-4"
              >
                <el-icon size="32" class="text-blue-400">
                  <Microphone />
                </el-icon>
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

      <!-- 📌 媒体库 -->
      <template v-if="currentMenuIdx === 1">
        <h2 class="text-xl font-bold mb-4 text-white">{{ t('allMedia') }}</h2>

        <!-- 批量操作栏（可选） -->
        <BatchToolbar
          :batch-mode="isBatchMode"
          :selected-ids="selectedIds"
          @show-move-dialog="showBatchMoveDialog = true"
          @show-move-to-collection-dialog="showBatchMoveToCollectionDialog = true"
          @generate-subtitles="batchSubtitle"
          @delete-videos="batchDelete"
          @concat-videos="batchConcat"
        />

        <!-- 逐分类渲染 -->
        <section v-for="cat in filteredCategories" :key="cat.id" class="mb-10">
          <h3 class="text-lg font-semibold mb-3 text-white">
            {{ cat.name || t('uncategorized') }}
          </h3>

          <MediaItemCards
            :category="cat"
            view="grid"
            :batch-mode="isBatchMode"
            v-model:selected-ids="selectedIds"
            @generate-subtitle="generateSubtitle"
            @delete="deleteVideo"
            @open-collection="openCollection"
            @edit-thumbnail="onEditThumbnail"
            @collection-moved="handleCollectionMoved"
          />
        </section>
      </template>

      <!-- 📌 History 页面 - 只有认证用户才能访问 -->
      <template v-if="currentMenuIdx === 2 && isAuthenticated">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold text-white">
            {{ t('recentAccess') }} ({{ recentVideos.length }}{{ t('videosCount') }})
          </h2>
          <el-button
            v-if="!isLoadingHistory"
            @click="fetchRecentVideos"
            type="primary"
            size="small"
            class="!bg-blue-600 !border-blue-600 hover:!bg-blue-700"
          >
            {{ t('refresh') }}
          </el-button>
        </div>

        <!-- 加载状态 -->
        <div v-if="isLoadingHistory" class="flex items-center justify-center py-12">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
          <span class="ml-3 text-white/80">{{ t('loadingRecentVideos') }}</span>
        </div>

        <!-- 错误状态 -->
        <div v-else-if="historyError" class="flex items-center justify-center py-12">
          <div class="text-center">
            <p class="text-red-400 mb-4">{{ historyError }}</p>
            <el-button @click="fetchRecentVideos" type="primary" size="small">重试</el-button>
          </div>
        </div>

        <!-- 正常内容 -->
        <template v-else>
          <!-- 批量操作栏 -->
          <BatchToolbar
            :batch-mode="isBatchMode"
            :selected-ids="selectedIds"
            @show-move-dialog="showBatchMoveDialog = true"
            @show-move-to-collection-dialog="showBatchMoveToCollectionDialog = true"
            @generate-subtitles="batchSubtitle"
            @delete-videos="batchDelete"
            @concat-videos="batchConcat"
          />

          <!-- 视频网格 -->
          <div
            v-if="paginatedRecentVideos.length > 0"
            class="grid gap-5 grid-cols-[repeat(auto-fit,minmax(240px,300px))]"
          >
            <VideoCard
              v-for="video in paginatedRecentVideos"
              :key="video.id"
              :video="video"
              view="grid"
              :batch-mode="isBatchMode"
              :checked="selectedIds.includes(video.id)"
              @update:checked="
                (val) => {
                  if (val) selectedIds.push(video.id)
                  else selectedIds = selectedIds.filter((id) => id !== video.id)
                }
              "
              @edit-thumbnail="onEditThumbnail"
              @generate-subtitle="() => generateSubtitle(video)"
              @delete="() => deleteVideo(video)"
              @rename-video="handleVideoRenamed"
            />
          </div>

          <!-- 空状态 -->
          <div v-else class="flex items-center justify-center py-12">
            <div class="text-center">
              <p class="text-white/60 text-lg mb-2">{{ t('noRecentVideos') }}</p>
              <p class="text-white/40 text-sm">{{ t('noRecentVideosDesc') }}</p>
            </div>
          </div>

          <!-- 分页组件 -->
          <div v-if="totalHistoryPages > 1" class="flex justify-center mt-6">
            <el-pagination
              v-model:current-page="currentPage"
              :total="recentVideos.length"
              :page-size="itemsPerPage"
              layout="prev, pager, next"
              :pager-count="7"
              class="pagination-custom"
            />
          </div>
        </template>
      </template>

      <!-- 📌 History 页面 - 未认证用户显示提示 -->
      <template v-if="currentMenuIdx === 2 && !isAuthenticated">
        <div class="flex items-center justify-center py-12">
          <div class="text-center">
            <p class="text-white/60 text-lg mb-2">{{ t('pleaseLogin') }}</p>
            <p class="text-white/40 text-sm">{{ t('pleaseLoginDesc') }}</p>
          </div>
        </div>
      </template>

      <!-- 📌 单一分类 -->
      <template v-else-if="currentMenuIdx === -1 && currentCategory">
        <h2 class="text-3xl font-bold mb-4 text-white">{{ currentCategory.name }}</h2>

        <BatchToolbar
          :batch-mode="isBatchMode"
          :selected-ids="selectedIds"
          @show-move-dialog="showBatchMoveDialog = true"
          @show-move-to-collection-dialog="showBatchMoveToCollectionDialog = true"
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
          @open-collection="openCollection"
          @edit-thumbnail="onEditThumbnail"
          @collection-moved="handleCollectionMoved"
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
      <!-- 📌 ③ Collection 详情 -->
      <template v-else-if="currentMenuIdx === 10 && currentCollection">
        <!-- 返回上一级 -->
        <el-button type="text" @click="returnFromCollection">
          ← {{ t('returnTo') }} {{ currentCategory?.name || t('library') }}
        </el-button>

        <h2 class="text-xl font-bold mb-4 text-white">{{ currentCollection.name }}</h2>

        <!-- 批量操作栏（可选） -->
        <BatchToolbar
          :batch-mode="isBatchMode"
          :selected-ids="selectedIds"
          @show-move-dialog="showBatchMoveDialog = true"
          @show-move-to-collection-dialog="showBatchMoveToCollectionDialog = true"
          @generate-subtitles="batchSubtitle"
          @delete-videos="batchDelete"
          @concat-videos="batchConcat"
        />

        <!-- 直接渲染 VideoCard 列表 -->
        <div class="grid gap-5 grid-cols-[repeat(auto-fit,minmax(240px,300px))]">
          <VideoCard
            v-for="video in paginatedCollectionVideos"
            :key="video.id"
            :video="video"
            view="grid"
            :batch-mode="isBatchMode"
            :checked="selectedIds.includes(video.id)"
            @update:checked="
              (val) => {
                if (val) selectedIds.push(video.id)
                else selectedIds = selectedIds.filter((id) => id !== video.id)
              }
            "
            @edit-thumbnail="onEditThumbnail"
            @generate-subtitle="() => generateSubtitle(video)"
            @delete="() => deleteVideo(video)"
            @rename-video="handleVideoRenamed"
          />
        </div>

        <!-- 分页组件 -->
        <div v-if="totalCollectionPages > 1" class="flex justify-center mt-6">
          <el-pagination
            v-model:current-page="currentPage"
            :total="currentCollectionVideos.length"
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

    <BatchMoveToCollectionDialog
      v-model="showBatchMoveToCollectionDialog"
      :selected-ids="selectedIds"
      @moved="onBatchMoved"
    />

    <EnhancedSubtitleDialog
      v-model="showSubtitleDialog"
      :video-id-list="selectedIds"
      :video-name-list="selectedVideos.map((v) => v.name)"
      @submitted="onSubtitleSubmitted"
    />

    <SettingsDialog
      v-model:visible="showSettingsDialog"
      :categories="categories"
      @categories-updated="onCategoriesUpdated"
    />

    <!-- Login Dialog -->
    <div
      v-if="showLoginDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showLoginDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-xl font-bold text-gray-800 mb-4">{{ t('login') }}</h2>
        <form @submit.prevent="handleLogin" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('username') }}</label>
            <input
              v-model="loginForm.username"
              type="text"
              class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              :placeholder="t('pleaseEnterUsername')"
              required
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('password') }}</label>
            <input
              v-model="loginForm.password"
              type="password"
              class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              :placeholder="t('pleaseEnterPassword')"
              required
            />
          </div>
          <div class="flex space-x-3 pt-4">
            <button
              type="button"
              @click="showLoginDialog = false"
              class="flex-1 px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
            >
              {{ t('cancel') }}
            </button>
            <button
              type="submit"
              class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              {{ t('login') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Register Dialog -->
    <div
      v-if="showRegisterDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showRegisterDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-xl font-bold text-gray-800 mb-2">{{ t('createRootUser') }}</h2>
        <p class="text-sm text-gray-600 mb-4">{{ t('noRootUserPrompt') }}</p>
        <form @submit.prevent="handleRegister" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('username') }}</label>
            <input
              v-model="registerForm.username"
              type="text"
              class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              :placeholder="t('pleaseEnterUsername')"
              required
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{
              t('emailOptional')
            }}</label>
            <input
              v-model="registerForm.email"
              type="email"
              class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              :placeholder="t('email')"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('password') }}</label>
            <input
              v-model="registerForm.password"
              type="password"
              class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              :placeholder="t('passwordHint')"
              required
            />
            <p class="text-xs text-gray-500 mt-1">{{ t('passwordRequirement') }}</p>
          </div>
          <div class="flex space-x-3 pt-4">
            <button
              type="button"
              @click="showRegisterDialog = false"
              class="flex-1 px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
            >
              {{ t('cancel') }}
            </button>
            <button
              type="submit"
              class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              {{ t('create') }}
            </button>
          </div>
        </form>
      </div>
    </div>

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
