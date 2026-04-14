<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from '@/composables/useNotification'
import { getCSRFToken } from '@/composables/GetCSRFToken'

import { BACKEND } from '@/composables/ConfigAPI'

// —— Props ——
const props = defineProps<{
  /** v-model 控制弹窗显隐 */
  modelValue: boolean
  /** 待处理视频 ID 列表  */
  videoIdList: number[]
  /** 与 videoIdList 一一对应的标题，用于后端记录 */
  videoNameList: string[]
}>()

// —— Emits ——
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  /** 后端提交成功后可通知父组件刷新 */
  (e: 'submitted'): void
}>()

// —— Dialog v-model 代理 ——
const visible = computed<boolean>({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// —— 表单状态 ——
const srcLang = ref<'zh' | 'en' | 'jp' | 'system_define'>('zh')
const transLang = ref<'none' | 'zh' | 'en' | 'jp'>('none')
const emphasizeSrc = ref('')
const emphasizeDst = ref('')
const loading = ref(false)

// —— 提交 ——
async function confirm() {
  if (!srcLang.value) {
    ElMessage.warning('请选择原文语言')
    return
  }

  loading.value = true

  try {
    const csrfToken = await getCSRFToken()
    const res = await fetch(`${BACKEND}/api/tasks/subtitle_generate/add`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({
        video_id_list: props.videoIdList,
        video_name_list: props.videoNameList,
        src_lang: srcLang.value,
        trans_lang: transLang.value === 'none' ? '' : transLang.value,
        emphasize_src: emphasizeSrc.value,
        emphasize_dst: emphasizeDst.value,
      }),
    })

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    ElMessage.success('已提交生成任务')
    emit('submitted')
    emit('update:modelValue', false)
  } catch (err: any) {
    console.error(err)
    ElMessage.error(`提交失败：${err.message}`)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="批量生成字幕" width="420px">
    <div class="space-y-3">
      <!-- 原文语言选择 -->
      <el-select v-model="srcLang" placeholder="原文语言">
        <el-option label="中文 (zh)" value="zh" />
        <el-option label="English (en)" value="en" />
        <el-option label="日本語 (jp)" value="jp" />
        <el-option label="System Define" value="system_define" />
      </el-select>

      <!-- 译文语言选择 -->
      <el-select v-model="transLang" placeholder="译文语言">
        <el-option label="无 (None)" value="none" />
        <el-option label="中文 (zh)" value="zh" />
        <el-option label="English (en)" value="en" />
        <el-option label="日本語 (jp)" value="jp" />
      </el-select>

      <!-- 原文强调名词 -->
      <el-input
        v-model="emphasizeSrc"
        type="textarea"
        :rows="2"
        placeholder="原文中需强调的名词（仅本地记录，可留空）"
      />

      <!-- 译文强调名词 -->
      <el-input
        v-model="emphasizeDst"
        type="textarea"
        :rows="2"
        placeholder="译文中需强调的名词（仅本地记录，可留空）"
      />
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="confirm">确定</el-button>
    </template>
  </el-dialog>
</template>
