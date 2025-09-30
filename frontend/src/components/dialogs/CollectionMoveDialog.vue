<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { Collection } from '@/types/media'

import { BACKEND } from '@/composables/ConfigAPI'
import { getCSRFToken } from '@/composables/GetCSRFToken'

const props = defineProps<{
  modelValue: boolean
  collection: Collection | null
  categories: { id: number; name: string }[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'moved'): void
}>()

const targetCategoryId = ref<number>(0)

async function confirm() {
  if (!props.collection) {
    ElMessage.warning('未选择合集')
    return
  }

  // No need to check for null since we use 0 for "未分类"

  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/collection/move_category/${props.collection.id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({
        category_id: targetCategoryId.value === 0 ? null : targetCategoryId.value,
      }),
    })

    const result = await response.json()
    if (result.success) {
      ElMessage.success('移动成功')
      emit('moved')
      emit('update:modelValue', false)
    } else {
      ElMessage.error(result.message || '移动失败')
    }
  } catch (error) {
    console.error('Move collection error:', error)
    ElMessage.error('网络错误，请重试')
  }
}
</script>

<template>
  <el-dialog
    title="移动合集到分类"
    width="320px"
    :model-value="modelValue"
    @update:modelValue="emit('update:modelValue', $event)"
  >
    <div v-if="collection" class="mb-4">
      <p class="text-sm text-gray-600 mb-2">合集：{{ collection.name }}</p>
    </div>

    <el-select v-model="targetCategoryId" placeholder="请选择目标分类" class="w-full mb-4">
      <el-option
        v-for="category in categories"
        :key="category.id"
        :label="category.name"
        :value="category.id"
      />
    </el-select>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="confirm">确定</el-button>
    </template>
  </el-dialog>
</template>
