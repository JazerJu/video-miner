<script setup lang="ts">
import { VideoPlay, More, VideoCamera, EditPen } from '@element-plus/icons-vue'
import { SquarePen, Play, Upload, Headphones, Link } from 'lucide-vue-next'
import { PictureFilled } from '@element-plus/icons-vue'
import { computed, ref, nextTick } from 'vue'
import type { Video } from '@/types/media'
import { getCSRFToken } from '@/composables/GetCSRFToken'
import { useNotification } from '@/composables/useNotification'
import { BACKEND } from '@/composables/ConfigAPI'

const props = defineProps<{
  video: Video
  view: 'grid' | 'list'
  batchMode?: boolean
  checked?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit-thumbnail', video: Video): void
  (e: 'generate-subtitle', video: Video): void
  (e: 'delete', video: Video): void
  (e: 'move-category', video: Video): void
  (e: 'update:checked', v: boolean): void
  (e: 'rename-video', video: Video, newName: string): void
  (e: 'update-props', video: Video): void
}>()

const { success: successNotify, error: errorNotify, warning: warningNotify } = useNotification()

const FALLBACK_IMG =
  'https://pic.chaopx.com/chao_water_pic/23/03/03/e78a5cf45f9ebc92411a8f9531975dec.jpg'

const watchUrl = computed(() => `watch/${encodeURIComponent(props.video.url)}`)
const filename = props.video.thumbnail_url || props.video.thumbnail || ''
const thumbnailUrl = computed(() =>
  filename ? `${BACKEND}/media/thumbnail/${encodeURIComponent(filename)}` : ''
)

// ── Inline rename ──────────────────────────────────────────────
const isEditing = ref(false)
const editingName = ref('')
const inputRef = ref<HTMLInputElement>()

const startEditing = async () => {
  isEditing.value = true
  editingName.value = props.video.name
  await nextTick()
  inputRef.value?.focus()
  inputRef.value?.select()
}

const saveEdit = async () => {
  const newName = editingName.value.trim()
  if (!newName) { warningNotify('名称不能为空'); return }
  if (newName === props.video.name) { isEditing.value = false; return }
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/${props.video.id}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      credentials: 'include',
      body: JSON.stringify({ videoId: props.video.id, newName }),
    })
    const result = await response.json()
    if (result.success) {
      emit('rename-video', props.video, newName)
      isEditing.value = false
      successNotify('重命名成功')
    } else {
      errorNotify(result.message || '重命名失败')
    }
  } catch {
    errorNotify('网络错误，请重试')
  }
}

const cancelEdit = () => { isEditing.value = false; editingName.value = '' }

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') saveEdit()
  else if (event.key === 'Escape') cancelEdit()
}

// ── Video properties dialog ────────────────────────────────────
const showPropsDialog = ref(false)
const propsForm = ref({ rawLang: '', videoSource: '', sourceUrl: '' })
const propsSaving = ref(false)

const openPropsDialog = () => {
  propsForm.value = {
    rawLang: props.video.rawLang || '',
    videoSource: props.video.videoSource || '',
    sourceUrl: props.video.sourceUrl || '',
  }
  showPropsDialog.value = true
}

const saveProps = async () => {
  propsSaving.value = true
  try {
    const csrf = await getCSRFToken()
    const res = await fetch(`${BACKEND}/api/videos/${props.video.id}/props`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      credentials: 'include',
      body: JSON.stringify({
        raw_lang: propsForm.value.rawLang,
        video_source: propsForm.value.videoSource,
        source_url: propsForm.value.sourceUrl,
      }),
    })
    const result = await res.json()
    if (result.success) {
      props.video.rawLang = result.raw_lang
      props.video.videoSource = result.video_source
      props.video.sourceUrl = result.source_url
      emit('update-props', props.video)
      showPropsDialog.value = false
      successNotify('属性已保存')
    } else {
      errorNotify(result.error || '保存失败')
    }
  } catch {
    errorNotify('网络错误，保存失败')
  } finally {
    propsSaving.value = false
  }
}

const openEditor = () => {
  window.location.href = '/editor/' + encodeURIComponent(props.video.url)
}

const modelChecked = computed({
  get: () => props.checked ?? false,
  set: (v) => emit('update:checked', v),
})

const PLATFORM_OPTIONS = [
  { value: 'bilibili', label: 'Bilibili' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'podcast', label: 'Podcast' },
  { value: 'upload', label: 'Upload' },
]

const LANG_OPTIONS = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'jp', label: '日本語' },
]
</script>

<template>
  <!-- ───────────── GRID STYLE ───────────── -->
  <div
    v-if="view === 'grid'"
    class="video-card-hover relative bg-gray-500/30 rounded-2xl overflow-hidden border border-gray-400/30 shadow-lg hover:shadow-xl group transition-all duration-300 hover:transform hover:scale-105"
    :class="checked ? 'border-[rgb(34,124,46)] border-2' : ''"
  >
    <el-checkbox
      v-model="modelChecked"
      :label="''"
      class="video-select !absolute top-1.5 left-1.5 z-30 transition-opacity opacity-0 group-hover:opacity-100"
      :class="batchMode ? '!opacity-100' : ''"
    />
    <img :src="thumbnailUrl || FALLBACK_IMG" class="w-full h-40 object-cover" :alt="video.name" />
    <div
      v-if="video.length"
      class="absolute top-2 right-2 bg-blue-500/90 text-white text-sm font-medium px-3 py-1 rounded-md"
    >
      {{ video.length }}
    </div>
    <div
      class="absolute left-0 right-0 top-0 h-40 bg-black/30 backdrop-blur-[1px] flex items-center justify-center opacity-0 hover:opacity-100 transition-all duration-300"
    >
      <a
        :href="watchUrl"
        class="w-12 h-12 rounded-full bg-blue-500/80 flex items-center justify-center hover:bg-blue-500/90 transition-all cursor-pointer"
      >
        <Play :size="24" class="text-white ml-1" />
      </a>
    </div>

    <div class="p-4">
      <div v-if="!isEditing" class="flex items-center gap-2 mb-2">
        <el-tooltip :content="video.name" placement="top">
          <h3 class="font-semibold text-white truncate flex-1 text-lg">
            <a :href="watchUrl" class="no-underline text-inherit hover:text-blue-300 transition-colors">
              {{ video.name }}
            </a>
          </h3>
        </el-tooltip>
        <div class="opacity-0 group-hover:opacity-100 transition-all duration-200">
          <el-dropdown trigger="click">
            <button class="text-white hover:text-blue-300 transition-colors p-1">
              <el-icon class="text-xl"><More /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="emit('edit-thumbnail', video)">
                  <el-icon><PictureFilled /></el-icon>
                  <span style="margin-left: 4px">更换预览图</span>
                </el-dropdown-item>
                <el-dropdown-item @click="openEditor">
                  <el-icon class="mr-2"><EditPen /></el-icon> 字幕/音频编辑
                </el-dropdown-item>
                <el-dropdown-item @click="startEditing" divided>
                  <SquarePen class="w-4 h-4 mr-2" /> 重命名
                </el-dropdown-item>
                <el-dropdown-item @click="openPropsDialog">
                  <Link class="w-4 h-4 mr-2" /> 视频属性
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
      <div v-else class="flex items-center gap-2 mb-2">
        <input
          ref="inputRef"
          v-model="editingName"
          class="flex-1 font-semibold text-white bg-white/20 backdrop-blur-sm border border-white/30 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent placeholder-white/50"
          @keydown="handleKeydown"
          @blur="saveEdit"
        />
      </div>
      <p class="text-white/70 text-sm mb-4 line-clamp-2">{{ video.description }}</p>
      <div class="flex justify-between items-center pt-3 border-t border-white/20">
        <span class="text-xs text-white/60">{{ video.last_modified }}</span>
      </div>
    </div>
  </div>

  <!-- ───────────── LIST STYLE ───────────── -->
  <div
    v-else
    class="flex items-center justify-between p-4 hover:bg-gray-50 border-b border-gray-100 last:border-0"
  >
    <div class="flex items-center gap-4">
      <div class="relative">
        <img
          :src="thumbnailUrl || FALLBACK_IMG"
          class="w-20 h-12 rounded object-cover"
          :alt="video.name"
        />
        <div
          class="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity bg-black/30"
        >
          <a :href="watchUrl">
            <el-button type="primary" circle class="!w-8 !h-8">
              <el-icon class="text-lg"><VideoPlay /></el-icon>
            </el-button>
          </a>
        </div>
      </div>

      <div>
        <div v-if="!isEditing" class="flex items-center gap-2">
          <el-tooltip :content="video.name" placement="top">
            <div class="font-medium text-textmain">{{ video.name }}</div>
          </el-tooltip>
        </div>
        <div v-else class="flex items-center gap-2">
          <input
            ref="inputRef"
            v-model="editingName"
            class="font-medium text-textmain bg-white border border-blue-300 rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
            @keydown="handleKeydown"
            @blur="saveEdit"
          />
        </div>
        <div class="text-xs text-gray-500 flex items-center gap-3 mt-1">
          <span>{{ video.last_modified }}</span>
          <span>•</span>
          <span>{{ video.length }}</span>
        </div>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <a :href="watchUrl" class="no-underline text-inherit">
        <el-tag type="info" size="small" class="!flex !items-center">
          <el-icon class="mr-1"><VideoCamera /></el-icon> 视频
        </el-tag>
      </a>
      <el-dropdown trigger="click">
        <el-button circle class="!w-8 !h-8">
          <el-icon><More /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="emit('edit-thumbnail', video)">
              <el-icon class="mr-2"><PictureFilled /></el-icon> 更换预览图
            </el-dropdown-item>
            <el-dropdown-item @click="openEditor">
              <el-icon class="mr-2"><EditPen /></el-icon> 字幕/音频编辑
            </el-dropdown-item>
            <el-dropdown-item @click="startEditing" divided>
              <SquarePen class="w-4 h-4 mr-2" /> 重命名
            </el-dropdown-item>
            <el-dropdown-item @click="openPropsDialog">
              <Link class="w-4 h-4 mr-2" /> 视频属性
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>

  <!-- ───────────── Video Properties Dialog ───────────── -->
  <el-dialog
    v-model="showPropsDialog"
    title="视频属性"
    width="420px"
    @close="showPropsDialog = false"
  >
    <div class="space-y-5">
      <!-- 原始语言 -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">原始语言</label>
        <el-select v-model="propsForm.rawLang" placeholder="不设置" clearable class="w-full">
          <el-option
            v-for="opt in LANG_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>

      <!-- 源平台 -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">源平台</label>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="p in PLATFORM_OPTIONS"
            :key="p.value"
            @click="propsForm.videoSource = propsForm.videoSource === p.value ? '' : p.value"
            :class="[
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm transition-all',
              propsForm.videoSource === p.value
                ? 'border-blue-500 bg-blue-50 text-blue-600 font-medium'
                : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300',
            ]"
          >
            <!-- Bilibili icon -->
            <svg v-if="p.value === 'bilibili'" class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M17.813 4.653h.854c1.51.054 2.769.578 3.773 1.574 1.004.995 1.524 2.249 1.56 3.76v7.36c-.036 1.51-.556 2.769-1.56 3.773s-2.262 1.524-3.773 1.56H5.333c-1.51-.036-2.769-.556-3.773-1.56S.036 18.858 0 17.347v-7.36c.036-1.511.556-2.765 1.56-3.76 1.004-.996 2.262-1.52 3.773-1.574h.774l-1.174-1.12a1.234 1.234 0 0 1 0-1.773 1.234 1.234 0 0 1 1.773 0l2.88 2.76h4.107l2.88-2.76a1.234 1.234 0 0 1 1.773 0 1.234 1.234 0 0 1 0 1.773zM5.333 7.24c-.853.036-1.548.32-2.08.853-.53.533-.808 1.227-.853 2.08v7.013c.045.853.322 1.544.853 2.08.532.533 1.227.81 2.08.853h13.334c.853-.043 1.544-.32 2.08-.853.535-.536.81-1.227.853-2.08V10.173c-.043-.853-.318-1.547-.853-2.08-.536-.533-1.227-.817-2.08-.853zM9.2 10.853v4.48c0 .32-.11.59-.333.8a1.106 1.106 0 0 1-.8.32 1.106 1.106 0 0 1-.8-.32 1.085 1.085 0 0 1-.333-.8v-4.48c0-.32.11-.59.333-.8.222-.213.48-.32.8-.32.32 0 .578.107.8.32.222.21.333.48.333.8zm7.466 0v4.48c0 .32-.11.59-.333.8a1.106 1.106 0 0 1-.8.32 1.106 1.106 0 0 1-.8-.32 1.085 1.085 0 0 1-.333-.8v-4.48c0-.32.11-.59.333-.8.222-.213.48-.32.8-.32.32 0 .578.107.8.32.222.21.333.48.333.8z"/>
            </svg>
            <!-- YouTube icon -->
            <svg v-else-if="p.value === 'youtube'" class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
            </svg>
            <!-- Podcast icon -->
            <Headphones v-else-if="p.value === 'podcast'" class="w-4 h-4" />
            <!-- Upload icon -->
            <Upload v-else class="w-4 h-4" />
            {{ p.label }}
          </button>
        </div>
      </div>

      <!-- 源链接 -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">源链接</label>
        <el-input
          v-model="propsForm.sourceUrl"
          placeholder="https://..."
          clearable
        />
      </div>
    </div>

    <template #footer>
      <el-button @click="showPropsDialog = false">取消</el-button>
      <el-button type="primary" :loading="propsSaving" @click="saveProps">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
@reference "../../assets/tailwind.css";

.video-card-hover:hover {
  @apply transition-shadow;
}

.video-select {
  margin: 0 !important;
  padding: 0 !important;
  height: 20px !important;
  background: transparent;
}

:deep(.video-select .el-checkbox__label) {
  display: none;
}

:deep(.video-select .el-checkbox__input) {
  width: 20px;
  height: 20px;
}

:deep(.video-select .el-checkbox__inner) {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.6);
  border-radius: 4px;
  background-color: rgba(0, 0, 0, 0.5);
  transition: all 0.2s ease;
}

:deep(.video-select .el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: rgb(34, 124, 46);
  border-color: rgb(34, 124, 46);
}

:deep(.video-select .el-checkbox__input.is-checked .el-checkbox__inner::after) {
  border-width: 0 2px 2px 0;
  left: 6px;
  top: 2px;
  width: 4px;
  height: 8px;
}
</style>
