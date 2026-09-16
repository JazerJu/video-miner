<script setup lang="ts">
/**
 * Floating table of contents, like the Obsidian floating-toc plugin.
 *
 * Collapsed it is a column of short bars in the empty margin, one per heading.
 * On hover it opens into the heading list. The heading under the top of the
 * window stays highlighted while the page scrolls.
 */
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  /** Element holding the rendered markdown. */
  container: HTMLElement | null
  /** Sticky header height, so a heading does not land under it. */
  offset?: number
  /** Re-read the headings whenever this changes. */
  source?: string
  /** Which heading levels to list. The summary repeats the same h3 in every chapter. */
  levels?: string
}>(), { offset: 72, source: '', levels: 'h1, h2' })

type Item = { id: string; text: string; level: number }

const items = ref<Item[]>([])
const activeId = ref('')
const open = ref(false)

function slug(text: string, index: number) {
  const base = text.toLowerCase().trim().replace(/[^\w一-鿿]+/g, '-').replace(/^-+|-+$/g, '')
  return `toc-${index}-${base.slice(0, 40) || 'section'}`
}

function scan() {
  const root = props.container
  if (!root) {
    items.value = []
    return
  }
  const found: Item[] = []
  root.querySelectorAll<HTMLElement>(props.levels).forEach((el, i) => {
    const text = (el.textContent || '').trim()
    if (!text) return
    if (!el.id) el.id = slug(text, i)
    found.push({ id: el.id, text, level: Number(el.tagName[1]) })
  })
  items.value = found
  updateActive()
}

function updateActive() {
  const root = props.container
  if (!root || !items.value.length) return
  let current = items.value[0].id
  for (const item of items.value) {
    const el = document.getElementById(item.id)
    if (el && el.getBoundingClientRect().top <= props.offset + 8) current = item.id
    else break
  }
  activeId.value = current
}

let ticking = false
function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => {
    updateActive()
    ticking = false
  })
}

let correcting = 0
function cancelCorrection() {
  clearTimeout(correcting)
}

function jump(item: Item) {
  const scrollToHeading = (smooth: boolean) => {
    const el = document.getElementById(item.id)
    if (!el) return 0
    const delta = el.getBoundingClientRect().top - props.offset
    if (Math.abs(delta) > 4) {
      window.scrollTo({ top: window.scrollY + delta, behavior: smooth ? 'smooth' : 'auto' })
    }
    return delta
  }
  scrollToHeading(true)
  activeId.value = item.id
  // 摘要里的截图是后加载的，加载完页面会被撑开，落点要再校正一次
  cancelCorrection()
  correcting = window.setTimeout(() => {
    if (Math.abs(scrollToHeading(false)) > 4) {
      correcting = window.setTimeout(() => scrollToHeading(false), 700)
    }
  }, 600)
}

watch(() => [props.container, props.source], () => nextTick(scan), { immediate: true })
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  // 用户自己滚了就别再纠正落点
  window.addEventListener('wheel', cancelCorrection, { passive: true })
  window.addEventListener('touchstart', cancelCorrection, { passive: true })
})
onBeforeUnmount(() => {
  cancelCorrection()
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('wheel', cancelCorrection)
  window.removeEventListener('touchstart', cancelCorrection)
})
</script>

<template>
  <nav
    v-if="items.length > 1"
    class="fixed left-2 top-1/2 z-20 -translate-y-1/2 max-xl:hidden"
    @mouseenter="open = true"
    @mouseleave="open = false"
    aria-label="Summary outline"
  >
    <!-- collapsed: one bar per heading, indented by level -->
    <div v-show="!open" class="flex flex-col gap-2 py-2 pl-2 pr-6">
      <span
        v-for="item in items"
        :key="item.id"
        class="h-0.5 rounded-full transition-colors"
        :class="[
          item.level === 1 ? 'w-8' : item.level === 2 ? 'w-6' : 'w-4',
          item.id === activeId
            ? 'bg-blue-500 dark:bg-blue-400'
            : 'bg-slate-300 dark:bg-slate-600',
        ]"
        :style="{ marginLeft: `${(item.level - 1) * 6}px` }"
      ></span>
    </div>

    <!-- expanded: the heading list -->
    <div
      v-show="open"
      class="max-h-[80vh] w-72 overflow-y-auto rounded-lg border border-slate-200 bg-white/95 py-2 shadow-lg backdrop-blur dark:border-slate-700 dark:bg-slate-800/95"
    >
      <button
        v-for="item in items"
        :key="item.id"
        @click="jump(item)"
        :title="item.text"
        class="block w-full truncate px-3 py-1 text-left text-xs transition-colors"
        :class="[
          item.level === 2 ? 'pl-5' : item.level === 3 ? 'pl-7' : '',
          item.id === activeId
            ? 'bg-blue-50 font-medium text-blue-600 dark:bg-blue-950/40 dark:text-blue-400'
            : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700',
        ]"
      >
        {{ item.text }}
      </button>
    </div>
  </nav>
</template>
