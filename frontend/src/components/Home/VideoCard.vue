<script setup lang="ts">
import { VideoPlay, More, Delete, VideoCamera, EditPen } from '@element-plus/icons-vue'
import { SquarePen, Play, Sparkles, Music, Mic } from 'lucide-vue-next'
import { PictureFilled, Edit } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, nextTick } from 'vue'
import type { Video } from '@/types/media'
import { getCSRFToken } from '@/composables/GetCSRFToken'
/** ─ props ─────────────────────────────────────────────────────────────── */

const props = defineProps<{
  video: Video
  view: 'grid' | 'list'
  batchMode?: boolean /* ✨ 新增 */
  checked?: boolean /* ✨ 外部 v‑model */
}>()

/** ─ emits ─────────────────────────────────────────────────────────────── */
const emit = defineEmits<{
  (e: 'edit-thumbnail', video: Video): void
  (e: 'generate-subtitle', video: Video): void
  (e: 'delete', video: Video): void
  (e: 'move-category', video: Video): void
  (e: 'update:checked', v: boolean): void
  (e: 'rename-video', video: Video, newName: string): void
}>()

/**
 * Confirm and trigger audio conversion (video → audio, delete original video)
 */
// conversion helpers
const confirmConvertAudio = (video: Video) => {
  ElMessageBox.confirm('转换后将删除原始视频，仅保留音频文件，是否继续？', '转换为音频', {
    confirmButtonText: '转换',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      try {
        const csrf = await getCSRFToken()
        const res = await fetch(`${BACKEND}/api/convert-audio/${video.id}/`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'X-CSRFToken': csrf,
          },
        })
        const result = await res.json()
        if (result.success) {
          ElMessage.success('音频转换完成')
          // optionally emit event to refresh list
        } else {
          ElMessage.error(result.error || '音频转换失败')
        }
      } catch (err) {
        ElMessage.error('网络错误，转换失败')
        console.error('Convert audio error:', err)
      }
    })
    .catch(() => {
      /* canceled */
    })
}

/** Confirm and trigger HLS conversion (video → m3u8/ts) */
const confirmConvertHLS = (video: Video) => {
  ElMessageBox.confirm('转换后将生成 HLS (m3u8+ts)，是否继续？', '转换为 HLS', {
    confirmButtonText: '转换',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      try {
        const csrf = await getCSRFToken()
        const res = await fetch(`${BACKEND}/api/convert-hls/${video.id}`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'X-CSRFToken': csrf },
        })
        const result = await res.json()
        if (result.success) {
          ElMessage.success('HLS 转换完成')
        } else {
          ElMessage.error(result.error || 'HLS 转换失败')
        }
      } catch (err) {
        ElMessage.error('网络错误，转换失败')
      }
    })
    .catch(() => {})
}

/** TTS Dialog State */
const showTTSDialog = ref(false)
const ttsForm = ref({ language: 'zh', voice: 'longxiaochun_v2' })
const currentTTSVideo = ref<Video | null>(null)

// Voice options list
const voiceOptions = [
  { label: '龙小淳 (知性积极女)', value: 'longxiaochun_v2' },
  { label: 'Donna (美式英文女)', value: 'loongdonna_v2' },
  { label: 'David (美式英文男)', value: 'loongdavid_v2' },
  { label: 'Cally (美式英文女)', value: 'loongcally_v2' },
  { label: 'Stella (飒爽利落女)', value: 'loongstella_v2' },
  { label: '龙书 (沉稳青年男)', value: 'longshu_v2' },
  { label: 'Bella (精准干练女)', value: 'loongbella_v2' },
]

/** Generate TTS voiceover for video */
const generateTTSVoiceover = async (video: Video) => {
  currentTTSVideo.value = video
  ttsForm.value = { language: 'zh', voice: 'longxiaochun_v2' }
  showTTSDialog.value = true
  console.log(currentTTSVideo.value)
  console.log("showTTSDialog is true")
}

/** Submit TTS generation */
const submitTTSGeneration = async () => {
  if (!currentTTSVideo.value) return
  try {
    const csrf = await getCSRFToken()
    const res = await fetch(`${BACKEND}/api/tts/generate/${currentTTSVideo.value.id}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ language: ttsForm.value.language, voice: ttsForm.value.voice }),
    })
    const result = await res.json()
    if (result.success) {
      ElMessage.success(`TTS 任务已创建：${result.task_id}`)
      showTTSDialog.value = false
    } else if (result.error === 'no subtitle for this video') {
      ElMessage.error('该视频没有对应语言的字幕，请先生成字幕')
    } else {
      ElMessage.error(result.error || 'TTS 生成失败')
    }
  } catch (err) {
    ElMessage.error('网络错误，TTS 生成失败')
    console.error('TTS generation error:', err)
  }
}

const FALLBACK_IMG =
  'https://pic.chaopx.com/chao_water_pic/23/03/03/e78a5cf45f9ebc92411a8f9531975dec.jpg'

import { BACKEND } from '@/composables/ConfigAPI'

const watchUrl = computed(() => `watch/${encodeURIComponent(props.video.url)}`)
const filename = props.video.thumbnail ?? ''

// Inline editing state
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
  if (!newName) {
    ElMessage.warning('名称不能为空')
    return
  }
  if (newName === props.video.name) {
    isEditing.value = false
    return
  }

  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/videos/${props.video.id}/rename`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({ videoId: props.video.id, newName }),
    })

    const result = await response.json()
    if (result.success) {
      emit('rename-video', props.video, newName)
      isEditing.value = false
      ElMessage.success('重命名成功')
    } else {
      ElMessage.error(result.message || '重命名失败')
    }
  } catch (error) {
    ElMessage.error('网络错误，请重试')
    console.error('Rename error:', error)
  }
}

const cancelEdit = () => {
  isEditing.value = false
  editingName.value = ''
}

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') {
    saveEdit()
  } else if (event.key === 'Escape') {
    cancelEdit()
  }
}

const thumbnailUrl = `${BACKEND}/media/${encodeURIComponent(filename)}`

/* ✨ 双向绑定小助手 */
const modelChecked = computed({
  get: () => props.checked ?? false,
  set: (v) => emit('update:checked', v),
})
</script>

<template>
  <!-- ───────────── GRID STYLE (card) ───────────── -->
  <div
    v-if="view === 'grid'"
    class="video-card-hover relative bg-gray-500/30 rounded-2xl overflow-hidden border border-gray-400/30 shadow-lg hover:shadow-xl group transition-all duration-300 hover:transform hover:scale-105"
  >
    <el-checkbox
      v-model="modelChecked"
      :label="''"
      class="video-select !absolute top-3 left-3 z-30 transition-opacity opacity-0 group-hover:opacity-100"
      :class="batchMode ? 'opacity-100' : ''"
      size="large"
    />
    <img :src="thumbnailUrl || FALLBACK_IMG" class="w-full h-40 object-cover" :alt="video.name" />
    <div
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
            <a
              :href="watchUrl"
              class="no-underline text-inherit hover:text-blue-300 transition-colors"
            >
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
                  <el-icon style="margin-left: -8px; font-size: 0.75em"><Edit /></el-icon>
                  <span style="margin-left: 4px">更换预览图</span>
                </el-dropdown-item>

                <el-dropdown-item>
                  <a
                    :href="'/editor/' + encodeURIComponent(video.url)"
                    class="flex items-center w-full"
                  >
                    <el-icon class="mr-2"><EditPen /></el-icon> 编辑字幕
                  </a>
                </el-dropdown-item>

                <el-dropdown-item @click="emit('generate-subtitle', video)">
                  <Sparkles class="w-4 h-4 mr-2" /> 字幕操作
                </el-dropdown-item>
                <el-dropdown-item @click="generateTTSVoiceover(video)">
                  <Mic class="w-4 h-4 mr-2" /> TTS 配音
                </el-dropdown-item>
                <el-dropdown-item @click="confirmConvertAudio(video)">
                  <Music class="w-4 h-4 mr-2" /> 转换音频
                </el-dropdown-item>
                <el-dropdown-item @click="confirmConvertHLS(video)">
                  <VideoCamera class="w-4 h-4 mr-2" /> 转换为 HLS
                </el-dropdown-item>

                <el-dropdown-item @click="emit('delete', video)" divided class="text-red-500">
                  <el-icon class="mr-2"><Delete /></el-icon> 删除
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
      <p class="text-white/70 text-sm mb-4 line-clamp-2">
        {{ video.description }}
      </p>

      <div class="flex justify-between items-center pt-3 border-t border-white/20">
        <span class="text-xs text-white/60">{{ video.last_modified }}</span>
      </div>
    </div>

    <!-- Edit icon positioned at bottom right -->
    <div
      class="absolute bottom-3 right-3 opacity-0 group-hover:opacity-100 transition-all duration-200"
    >
      <button class="text-white hover:text-blue-300 transition-colors" @click.stop="startEditing">
        <SquarePen :size="20" class="text-white" />
      </button>
    </div>
  </div>

  <!-- ───────────── LIST STYLE (row) ───────────── -->
  <div
    v-else
    class="flex items-center justify-between p-4 hover:bg-gray-50 border-b border-gray-100 last:border-0"
  >
    <div class="flex items-center gap-4">
      <div class="relative">
        <img
          :src="video.thumbnail || FALLBACK_IMG"
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
          <el-icon
            class="w-4 h-4 opacity-50 hover:opacity-100 cursor-pointer"
            @click.stop="startEditing"
          >
            <EditPen />
          </el-icon>
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
              <el-icon class="mr-2"><EditPen /></el-icon> 更换预览图
            </el-dropdown-item>

            <el-dropdown-item>
              <a
                :href="'/editor/' + encodeURIComponent(video.url)"
                class="flex items-center w-full"
              >
                <el-icon class="mr-2"><EditPen /></el-icon> 编辑字幕
              </a>
            </el-dropdown-item>

            <el-dropdown-item @click="emit('generate-subtitle', video)">
              <Sparkles class="w-4 h-4 mr-2" /> 字幕操作
            </el-dropdown-item>
            <el-dropdown-item @click="generateTTSVoiceover(video)">
              <Mic class="w-4 h-4 mr-2" /> TTS 配音
            </el-dropdown-item>

            <el-dropdown-item @click="emit('delete', video)" divided class="text-red-500">
              <el-icon class="mr-2"><Delete /></el-icon> 删除
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
  <!-- TTS 配音 弹窗 -->
  <el-dialog v-model="showTTSDialog" title="TTS 配音" width="30%" @close="showTTSDialog = false">
    <el-form :model="ttsForm" label-width="80px">
      <el-form-item label="语言">
        <el-radio-group v-model="ttsForm.language">
          <el-radio label="zh">中文</el-radio>
          <el-radio label="en">英文</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="语音">
        <el-select v-model="ttsForm.voice" placeholder="选择语音">
          <el-option
            v-for="opt in voiceOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value">
          </el-option>
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showTTSDialog = false">取消</el-button>
      <el-button type="primary" @click="submitTTSGeneration">生成</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
@reference "../../assets/tailwind.css";

.video-card-hover:hover {
  @apply transition-shadow;
  /* shadow-lg  */
}

.video-select {
  margin: 0 !important;
  padding: 0 !important;
  background: transparent;
}

/* 深度选择内部生成的元素 */
:deep(.video-select .el-checkbox__label) {
  display: none;
}

:deep(.video-select .el-checkbox__inner) {
  border-radius: 4px;
  width: 20px;
  height: 20px;
  border: 2px solid rgba(59, 130, 246, 0.8);
  background-color: transparent;
}

:deep(.video-select .el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: #1e3a8a;
  border-color: #1e3a8a;
}

:deep(.video-select .el-checkbox__inner::after) {
  width: 6px;
  height: 10px;
  border-width: 0 2px 2px 0;
  left: 6px;
  top: 2px;
}
</style>
