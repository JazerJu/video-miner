<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'

const { t } = useI18n()
const router = useRouter()

import {
  LibraryBig,
  History,
  Home,
  Video,
  Settings,
  User,
  LogOut,
  ChevronUp,
  UserCircle,
  Bot,
  Monitor,
  Captions,
  Mic,
  Tag,
  Folder,
  KeyRound,
  Sun,
  Moon,
  Brain,
  ShieldCheck,
} from 'lucide-vue-next'
import { ElTooltip, ElMessageBox } from 'element-plus'
import { ElMessage } from '@/composables/useNotification'
import ProfileDialog from '@/components/dialogs/ProfileDialog.vue'
import { BACKEND } from '@/composables/ConfigAPI'
import { useTheme } from '@/composables/useTheme'

const { theme, toggleTheme } = useTheme()
const route = useRoute()

// 菜单列表 - 基于路由
const menuList = [
  { key: 'home', icon: Home, to: '/' },
  { key: 'library', icon: Video, to: '/library' },
]

// Settings Tabs - 固定显示，不随菜单切换
const settingsTabs = [
  { id: 'model', label: t('llmSettings'), icon: Bot },
  { id: 'videoUnderstanding', label: t('videoUnderstandingSettings'), icon: Brain },
  { id: 'interface', label: t('interfaceSettings'), icon: Monitor },
  { id: 'subtitle', label: t('subtitleSettings'), icon: Captions },
  { id: 'transcription', label: t('transcriptionSettings'), icon: Mic },
  { id: 'tags', label: t('tagManagement'), icon: Tag },
  { id: 'folders', label: t('folders'), icon: Folder },
  { id: 'media', label: t('mediaCredentials'), icon: KeyRound },
  { id: 'apiToken', label: t('apiTokenManagement'), icon: ShieldCheck },
]

const handleSettingsTabClick = (tab: string) => {
  router.push({ path: '/settings', query: { tab } })
}

// 折叠侧边栏
const collapsed = ref(false)
const toggleCollapse = () => (collapsed.value = !collapsed.value)

// User management
interface User {
  id: number
  username: string
  email: string
  is_root: boolean
  premium_authority: boolean
  is_active: boolean
}

const currentUser = ref<User | null>(null)
const showUserDropdown = ref(false)

const showProfileDialog = ref(false)

const checkUserStatus = async () => {
  try {
    const response = await fetch(`${BACKEND}/api/auth/profile/`, {
      credentials: 'include',
    })
    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        currentUser.value = data.user
      }
    }
  } catch (error) {
    console.error('Error checking user status:', error)
  }
}

const handleLogout = async () => {
  try {
    const response = await fetch(`${BACKEND}/api/auth/logout/`, {
      method: 'POST',
      credentials: 'include',
    })
    if (response.ok) {
      currentUser.value = null
      showUserDropdown.value = false
      ElMessage.success('已退出登录')
    }
  } catch (error) {
    console.error('Logout error:', error)
    ElMessage.error('退出登录失败')
  }
}

const handleUserAreaClick = async () => {
  if (currentUser.value) {
    showUserDropdown.value = !showUserDropdown.value
  } else {
    router.push('/login')
  }
}

const handleProfileClick = () => {
  showProfileDialog.value = true
  showUserDropdown.value = false
}

onMounted(() => {
  checkUserStatus()
})

watch(currentUser, (newUser, oldUser) => {
  if ((!oldUser && newUser) || (oldUser && !newUser)) {
    emit('refresh')
  }
})

const props = defineProps<{
  activeSettingsTab?: string
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'update-settings-tab', tab: string): void
}>()
</script>

<template>
  <div
    class="sidebar backdrop-blur-xl border-r flex flex-col h-full transition-all duration-300"
    :class="
      collapsed
        ? 'sidebar-collapsed bg-gradient-to-br from-slate-50 via-white to-slate-100 border-slate-200/80 dark:from-gray-900 dark:via-slate-900 dark:to-blue-900 dark:border-white/20'
        : 'sidebar-expanded bg-gradient-to-br from-slate-50 via-white to-slate-100 border-slate-200/80 dark:from-gray-900 dark:via-slate-900 dark:to-blue-900 dark:border-white/20'
    "
  >
    <!--缩起版 侧边栏-->
    <div v-if="collapsed" class="flex flex-col items-center py-6 space-y-6 flex-none px-2">
      <el-tooltip :content="t('displaySidebar')" placement="right">
        <button
          @click="toggleCollapse"
          class="text-slate-500 hover:text-slate-900 p-2 rounded-lg hover:bg-slate-100 dark:text-white/70 dark:hover:text-white dark:hover:bg-white/10 transition-all"
        >
          <LibraryBig :size="20" />
        </button>
      </el-tooltip>
      <el-tooltip :content="t('home')" placement="right">
        <router-link
          to="/"
          class="text-slate-500 hover:text-slate-900 p-2 rounded-lg hover:bg-slate-100 dark:text-white/70 dark:hover:text-white dark:hover:bg-white/10 transition-all"
        >
          <Home :size="20" />
        </router-link>
      </el-tooltip>
    </div>

    <!-- 展开版 侧边栏 -->
    <template v-if="!collapsed">
      <!-- Brand Header -->
      <div class="px-4 pt-5 pb-4 border-b border-slate-200/80 dark:border-white/10">
        <div class="flex items-center gap-2">
          <img
            class="h-10 w-10 shrink-0 p-0.5 border border-slate-200/80 dark:border-white/30 hover:border-teal-400/70 dark:hover:border-white/50 rounded-xl transition-all shadow-sm"
            src="@/assets/miner.png"
            alt="VideoMiner"
          />
          <div class="flex flex-col min-w-0">
            <span class="text-base font-semibold text-slate-950 dark:text-white truncate">{{
              t('brand')
            }}</span>
            <span
              class="inline-block self-start rounded-full border border-teal-500/20 bg-teal-500/10 px-2 py-0.5 text-[10px] font-semibold text-teal-700 dark:text-teal-200"
            >
              v1.0
            </span>
          </div>
          <div class="ml-auto flex items-center gap-1 shrink-0">
            <el-tooltip
              :content="theme === 'dark' ? t('switchToLightTheme') : t('switchToDarkTheme')"
              placement="top"
            >
              <button
                @click="toggleTheme"
                class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white/80 text-slate-600 shadow-sm hover:border-teal-400/60 hover:bg-teal-50 hover:text-teal-700 dark:border-white/10 dark:bg-white/5 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white transition-all"
              >
                <Sun v-if="theme === 'dark'" :size="18" />
                <Moon v-else :size="18" />
              </button>
            </el-tooltip>
            <el-tooltip :content="t('hideSidebar')" placement="top">
              <button
                @click="toggleCollapse"
                class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white/80 text-slate-600 shadow-sm hover:border-teal-400/60 hover:bg-teal-50 hover:text-teal-700 dark:border-white/10 dark:bg-white/5 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white transition-all"
              >
                <LibraryBig :size="20" />
              </button>
            </el-tooltip>
          </div>
        </div>
      </div>

      <div class="min-h-0 flex-1 flex flex-col py-4">
        <nav class="flex-none px-2">
          <!-- Menu items -->
          <div class="space-y-2 mb-6">
            <router-link
              v-for="(item, i) in menuList"
              :key="i"
              :to="item.to"
              class="flex items-center p-3 rounded-lg cursor-pointer transition-all duration-200"
              :class="
                route.path === item.to
                  ? 'bg-teal-600/90 text-white shadow-md'
                  : 'text-slate-700 hover:bg-slate-200/70 hover:text-slate-950 dark:text-white/80 dark:hover:bg-white/10 dark:hover:text-white'
              "
            >
              <div class="flex items-center">
                <component :is="item.icon" :size="18" />
                <span class="ml-3 font-medium">{{ t(item.key) }}</span>
              </div>
            </router-link>
          </div>
        </nav>

        <!-- Settings Tabs - 固定显示，不再随菜单切换 -->
        <div class="min-h-0 flex-1 flex flex-col px-2">
          <h6
            class="mb-4 px-2 text-xs font-semibold text-slate-500 dark:text-white/60 tracking-wide"
          >
            {{ t('settingsTitle') || '设置' }}
          </h6>
          <div class="settings-scroll min-h-0 flex-1 overflow-y-auto pr-1">
            <div
              v-for="tab in settingsTabs"
              :key="tab.id"
              class="p-3 mb-1 rounded-r-lg flex items-center cursor-pointer transition-all duration-200 border-l-3"
              :class="
                route.path === '/settings' && (route.query.tab || 'model') === tab.id
                  ? 'bg-teal-600/90 text-white border-l-cyan-300'
                  : 'text-slate-700 border-l-transparent hover:bg-slate-200/70 hover:border-l-teal-500/70 dark:text-white/80 dark:hover:bg-white/8 dark:hover:border-l-cyan-400/70'
              "
              @click="handleSettingsTabClick(tab.id)"
            >
              <component :is="tab.icon" :size="16" class="shrink-0" />
              <span class="font-medium ml-2">{{ tab.label }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottom User Status Area -->
      <div
        class="px-4 py-3 backdrop-blur-sm bg-white/75 dark:bg-white/5 border-t border-slate-200/80 dark:border-white/10"
      >
        <div
          @click="handleUserAreaClick"
          @touchstart="handleUserAreaClick"
          @touchend.prevent
          class="flex items-center p-3 rounded-xl cursor-pointer backdrop-blur-sm border border-slate-200/80 bg-white/80 hover:bg-slate-100 active:bg-slate-200 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10 dark:active:bg-white/20 transition-all duration-200 relative"
        >
          <div
            class="w-8 h-8 rounded-full bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center"
          >
            <User :size="16" class="text-white" />
          </div>
          <div class="ml-3 flex-1">
            <div v-if="currentUser" class="text-sm font-medium text-slate-900 dark:text-white">
              {{ currentUser.username }}
            </div>
            <div v-else class="text-sm font-medium text-slate-900 dark:text-white">
              {{ t('notLoggedIn') }}
            </div>
          </div>
          <ChevronUp
            v-if="currentUser"
            :size="16"
            class="text-slate-500 dark:text-white/60 transition-transform duration-200"
            :class="{ 'rotate-180': showUserDropdown }"
          />
        </div>

        <!-- User Dropdown -->
        <div
          v-if="currentUser && showUserDropdown"
          class="mt-2 bg-white/95 dark:bg-white/10 backdrop-blur-md rounded-xl border border-slate-200 dark:border-white/20 shadow-lg dark:shadow-none overflow-hidden"
        >
          <div
            @click="handleProfileClick"
            class="flex items-center px-3 py-2 hover:bg-slate-100 dark:hover:bg-white/10 cursor-pointer transition-colors"
          >
            <UserCircle :size="14" class="text-slate-600 dark:text-white/80 mr-3" />
            <span class="text-sm text-slate-700 dark:text-white/90">我的资料</span>
          </div>
          <div
            @click="handleLogout"
            class="flex items-center px-3 py-2 hover:bg-slate-100 dark:hover:bg-white/10 cursor-pointer transition-colors border-t border-slate-200 dark:border-white/10"
          >
            <LogOut :size="14" class="text-slate-600 dark:text-white/80 mr-3" />
            <span class="text-sm text-slate-700 dark:text-white/90">{{ t('logout') }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>

  <!-- Profile Dialog -->
  <ProfileDialog
    v-if="showProfileDialog"
    v-model:visible="showProfileDialog"
    @profile-updated="checkUserStatus"
  />
</template>

<style lang="postcss" scoped>
@reference "../../assets/tailwind.css";
@tailwind utilities;

.sidebar nav,
.sidebar .settings-scroll {
  scrollbar-width: thin;
  scrollbar-color: #e5e7eb transparent;
}

.sidebar nav::-webkit-scrollbar,
.sidebar .settings-scroll::-webkit-scrollbar {
  width: 6px;
}
.sidebar nav::-webkit-scrollbar-thumb,
.sidebar .settings-scroll::-webkit-scrollbar-thumb {
  background-color: #e5e7eb;
  border-radius: 3px;
}
.sidebar nav::-webkit-scrollbar-track,
.sidebar .settings-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-expanded {
  width: 28%;
}

.sidebar-collapsed {
  width: 8%;
}

@media (min-width: 1024px) {
  .sidebar-expanded {
    width: 14%;
  }
  .sidebar-collapsed {
    width: 4%;
  }
}
</style>
