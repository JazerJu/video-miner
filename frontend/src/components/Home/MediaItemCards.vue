<!-- 媒体卡片显示 -->
<script setup lang="ts">
import VideoCard from '@/components/Home/VideoCard.vue'
import type { Video } from '@/types/media'

function toggle(id: number, checked: boolean) {
  const set = new Set(props.selectedIds)
  checked ? set.add(id) : set.delete(id)
  emit('update:selectedIds', [...set])
}



const props = defineProps<{
  category: { id: number | null; name: string; items: Video[] }
  view: 'grid' | 'list'
  batchMode?: boolean
  selectedIds?: number[]
}>()

const emit = defineEmits<{
  (e: 'generate-subtitle', video: Video): void
  (e: 'delete', video: Video): void
  (e: 'thumbnail-updated', video: Video): void
  (e: 'category-moved', p: { videoId: number; categoryId: number | null }): void
  (e: 'update:selectedIds', v: number[]): void
  (e: 'edit-thumbnail', target: Video): void
}>()

</script>

<template>
  <!-- grid or list of cards -->
  <div v-if="view === 'grid'" class="grid gap-5 grid-cols-[repeat(auto-fit,minmax(240px,300px))]">
    <template v-for="item in props.category.items" :key="item.id">
      <!-- Video -->
      <VideoCard
        :video="item"
        :view="view"
        :batch-mode="props.batchMode"
        :checked="props.selectedIds?.includes(item.id) ?? false"
        @edit-thumbnail="emit('edit-thumbnail', $event)"
        @update:checked="toggle(item.id, $event)"
        @generate-subtitle="emit('generate-subtitle', item)"
        @delete="emit('delete', item)"
      />
    </template>
  </div>
</template>