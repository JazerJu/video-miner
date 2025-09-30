<script setup lang="ts">
import type { Collection } from '@/types/media'
import { More, EditPen, Folder } from '@element-plus/icons-vue'
import { SquarePen } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import CollectionMoveDialog from '@/components/dialogs/CollectionMoveDialog.vue'
import { ref, nextTick } from 'vue'
import { getCSRFToken } from '@/composables/GetCSRFToken'

const props = defineProps<{ col: Collection; view: 'grid' | 'list' }>()
const content = `${props.col.videos.length}个视频`
import { BACKEND } from '@/composables/ConfigAPI'
const thumbnailUrl = `${BACKEND}/media/${encodeURIComponent(props.col.thumbnail)}`
const FALLBACK_IMG =
  'https://pic.chaopx.com/chao_water_pic/23/03/03/e78a5cf45f9ebc92411a8f9531975dec.jpg'

// Inline editing state
const isEditing = ref(false)
const editingName = ref('')
const inputRef = ref<HTMLInputElement>()

// Collection move dialog state
const showCollectionMoveDialog = ref(false)
const categories = ref<{ id: number; name: string }[]>([])
const isLoadingCategories = ref(false)

const emit = defineEmits<{
  (e: 'edit-thumbnail', collection: Collection): void
  (e: 'open-collection', id: number): void
  (e: 'delete-collection', collection: Collection): void
  (e: 'rename-collection', collection: Collection, newName: string): void
  (e: 'collection-moved', collection: Collection): void
}>()

const handleDelete = () => {
  if (props.col.videos.length > 0) {
    ElMessage.warning('请先移动视频到其他合集')
    return
  }
  ElMessageBox.confirm(`确定要删除合集 "${props.col.name}" 吗？`, '删除合集', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      try {
        const csrf = await getCSRFToken()
        const response = await fetch(`${BACKEND}/api/collection/delete/${props.col.id}`, {
          method: 'DELETE',
          headers: {
            'X-CSRFToken': csrf,
          },
          credentials: 'include',
        })

        const result = await response.json()
        if (result.success) {
          ElMessage.success('合集删除成功')
          emit('delete-collection', props.col)
        } else {
          ElMessage.error(result.message || '删除失败')
        }
      } catch (error) {
        ElMessage.error('网络错误，请重试')
        console.error('Delete error:', error)
      }
    })
    .catch(() => {
      // 用户取消删除
    })
}

const startEditing = async () => {
  isEditing.value = true
  editingName.value = props.col.name
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
  if (newName === props.col.name) {
    isEditing.value = false
    return
  }

  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/collection/rename/${props.col.id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({ newName }),
    })

    const result = await response.json()
    if (result.success) {
      emit('rename-collection', props.col, newName)
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

const openCollectionMoveDialog = async () => {
  if (isLoadingCategories.value) return

  isLoadingCategories.value = true
  try {
    const response = await fetch(`${BACKEND}/api/category/query/0`)
    const result = await response.json()

    if (result.success) {
      categories.value = [
        { id: 0, name: '未分类' },
        ...result.categories.map((cat: any) => ({
          id: cat.id || 0,
          name: cat.name,
        })),
      ]
      showCollectionMoveDialog.value = true
    } else {
      ElMessage.error('获取分类列表失败')
    }
  } catch (error) {
    console.error('Fetch categories error:', error)
    ElMessage.error('获取分类列表失败')
  } finally {
    isLoadingCategories.value = false
  }
}

const onCollectionMoved = () => {
  showCollectionMoveDialog.value = false
  emit('collection-moved', props.col)
}
</script>

<template>
  <div
    class="collection-card relative bg-gray-500/30 backdrop-blur-md rounded-2xl shadow-lg hover:shadow-xl transition-all duration-300 hover:transform hover:scale-105 p-0 overflow-hidden border border-gray-400/30 group"
  >
    <!-- 顶部合集标签 -->
    <div
      class="absolute top-3 left-3 flex items-center space-x-1 bg-blue-100 text-blue-600 text-xs px-2 py-0.5 rounded-full z-20"
    >
      <el-icon class="w-3 h-3"><Folder /></el-icon>
      <span> 合集 </span>
    </div>

    <div class="relative h-48 bg-gray-100">
      <img :src="thumbnailUrl || FALLBACK_IMG" alt="封面" class="w-full h-full object-cover" />
      <!-- 视频数悬浮右下 -->
      <div
        class="absolute bottom-3 right-3 bg-blue-600 text-white text-xs rounded-full px-2 py-0.5"
      >
        {{ content }}
      </div>
    </div>

    <!-- 文案区 -->
    <div class="p-4 flex flex-col flex-1">
      <div class="flex items-center justify-between">
        <div v-if="!isEditing" class="flex items-center gap-2 flex-1">
          <h3
            class="text-xl font-semibold text-white truncate cursor-pointer hover:text-blue-300 transition-colors flex-1"
            @click.stop="emit('open-collection', col.id)"
          >
            {{ col.name }}
          </h3>
          <div class="opacity-0 group-hover:opacity-100 transition-all duration-200">
            <el-dropdown trigger="click">
              <button class="text-white hover:text-blue-300 transition-colors p-1">
                <el-icon class="text-xl"><More /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="openCollectionMoveDialog">
                    <el-icon class="mr-2"><EditPen /></el-icon> 移动至分类
                  </el-dropdown-item>
                  <el-dropdown-item @click="emit('edit-thumbnail', col)">
                    <el-icon class="mr-2"><EditPen /></el-icon> 更换预览图
                  </el-dropdown-item>
                  <!-- 无视频时可删；否则提示"请先移动视频" -->
                  <el-dropdown-item @click="handleDelete" divided>
                    <el-icon class="mr-2"><EditPen /></el-icon> 删除合集
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
        <div v-else class="flex items-center gap-2 flex-1">
          <input
            ref="inputRef"
            v-model="editingName"
            class="flex-1 text-lg font-semibold text-white bg-white/20 backdrop-blur-sm border border-white/30 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent placeholder-white/50"
            @keydown="handleKeydown"
            @blur="saveEdit"
          />
        </div>
      </div>

      <div class="flex justify-between items-center pt-3 border-t border-white/20">
        <span class="text-xs text-white/60">{{ col.last_modified }}</span>
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

    <!-- Collection Move Dialog -->
    <CollectionMoveDialog
      v-model="showCollectionMoveDialog"
      :collection="col"
      :categories="categories"
      @moved="onCollectionMoved"
    />
  </div>
</template>
