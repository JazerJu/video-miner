<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()

import {
  LibraryBig,
  Search as LucideSearch,
  History,
  Home,
  Video,
  Settings,
  User,
  UserPlus,
  LogOut,
  ChevronUp,
  UserCircle,
} from 'lucide-vue-next'
import { ElMessage, ElTooltip, ElMessageBox } from 'element-plus'
import UsersDialog from '@/components/dialogs/UsersDialog.vue'
import ProfileDialog from '@/components/dialogs/ProfileDialog.vue'
import { BACKEND } from '@/composables/ConfigAPI'

// 菜单列表 - 移除了 Settings，因为 Sidebar 固定显示 Settings
const menuList = [
  { key: 'home', icon: Home, action: () => emit('updateMenuIndex', 0) },
  { key: 'library', icon: Video, action: () => emit('updateMenuIndex', 1) },
  { key: 'search', icon: LucideSearch, action: openSearch, tooltip: 'Ctrl+K' },
]

function openSearch() {
  emit('open-search')
}

// Settings Tabs - 固定显示，不随菜单切换
const settingsTabs = [
  { id: 'model', label: 'LLM 设置' },
  { id: 'interface', label: '界面设置' },
  { id: 'subtitle', label: '字幕设置' },
  { id: 'transcription', label: '转录设置' },
  { id: 'tags', label: '标签管理' },
  { id: 'media', label: '媒体认证' },
  { id: 'oss', label: 'OSS 服务' },
  { id: 'tts', label: 'TTS 配音' },
]

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
const showUsersDialog = ref(false)
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

const handleUserManagementClick = () => {
  showUsersDialog.value = true
  showUserDropdown.value = false
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
  currentMenuIdx: number
  activeSettingsTab?: string
}>()

const emit = defineEmits<{
  (e: 'updateMenuIndex', idx: number): void
  (e: 'open-search'): void
  (e: 'refresh'): void
  (e: 'update-settings-tab', tab: string): void
}>()
</script>

<template>
  <div
    class="sidebar bg-gradient-to-br from-gray-900 via-slate-900 to-blue-900 backdrop-blur-xl border-r border-white/20 flex flex-col h-full transition-all duration-300"
    :class="collapsed ? 'sidebar-collapsed' : 'sidebar-expanded'"
  >
    <!--缩起版 侧边栏-->
    <div v-if="collapsed" class="flex flex-col items-center py-6 space-y-6 flex-none px-2">
      <el-tooltip :content="t('displaySidebar')" placement="right">
        <button
          @click="toggleCollapse"
          class="text-white/70 hover:text-white p-2 rounded-lg hover:bg-white/10 transition-all"
        >
          <LibraryBig :size="20" />
        </button>
      </el-tooltip>
      <el-tooltip :content="t('home')" placement="right">
        <button
          @click="emit('updateMenuIndex', 0)"
          class="text-white/70 hover:text-white p-2 rounded-lg hover:bg-white/10 transition-all"
        >
          <Home :size="20" />
        </button>
      </el-tooltip>
      <el-tooltip content="Search (Ctrl+K)" placement="right">
        <button
          @click="openSearch"
          class="text-white/70 hover:text-white p-2 rounded-lg hover:bg-white/10 transition-all"
        >
          <LucideSearch :size="20" />
        </button>
      </el-tooltip>
    </div>

    <!-- 展开版 侧边栏 -->
    <template v-if="!collapsed">
      <!-- 加个空行美化排版 -->
      <div class="py-2"></div>
      <nav class="flex-none px-2">
        <!-- Menu items -->
        <div class="space-y-2 mb-6">
          <div
            v-for="(item, i) in menuList"
            :key="i"
            class="flex items-center p-3 rounded-xl cursor-pointer backdrop-blur-sm border border-white/10 shadow-sm transition-all duration-200"
            :class="
              props.currentMenuIdx === i
                ? 'bg-white/20 text-white border-white/30 shadow-lg'
                : 'hover:bg-white/10 text-white/80 hover:border-white/20 hover:shadow-md'
            "
            @click="item.action()"
          >
            <template v-if="item.tooltip">
              <el-tooltip :content="item.tooltip" placement="right">
                <div class="flex items-center">
                  <component :is="item.icon" :size="18" />
                  <span class="ml-3 font-medium">{{ t(item.key) }}</span>
                </div>
              </el-tooltip>
            </template>
            <template v-else>
              <div class="flex items-center">
                <component :is="item.icon" :size="18" />
                <span class="ml-3 font-medium">{{ t(item.key) }}</span>
              </div>
            </template>
          </div>
        </div>
      </nav>

       <!-- Settings Tabs - 固定显示，不再随菜单切换 -->
      <div class="flex-1 overflow-y-auto px-2">
        <h6 class="mb-4 px-2 text-xs font-semibold text-white/60 tracking-wide">
          {{ t('settingsTitle') || '设置' }}
        </h6>
        <div class="flex-1 overflow-y-auto">
          <div
            v-for="tab in settingsTabs"
            :key="tab.id"
            class="group p-3 mb-2 rounded-xl flex items-center cursor-pointer relative backdrop-blur-sm border border-white/10 shadow-sm transition-all duration-200"
            :class="
              props.activeSettingsTab === tab.id
                ? 'bg-white/25 text-white border-white/30 shadow-lg transform translate-x-1'
                : 'hover:bg-white/15 text-white/90 hover:border-white/20 hover:shadow-md hover:transform hover:translate-x-0.5'
            "
            @click="emit('updateMenuIndex', 3); emit('update-settings-tab', tab.id)"
          >
            <span class="font-medium ml-2">{{ tab.label }}</span>
          </div>
        </div>
      </div>

      <!-- User Status Area -->
      <div class="px-4 py-2 backdrop-blur-sm bg-white/5 border-t border-white/10">
        <div
          @click="handleUserAreaClick"
          @touchstart="handleUserAreaClick"
          @touchend.prevent
          class="flex items-center p-3 rounded-xl cursor-pointer backdrop-blur-sm border border-white/10 hover:bg-white/10 active:bg-white/20 transition-all duration-200 relative"
        >
          <div
            class="w-8 h-8 rounded-full bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center"
          >
            <User :size="16" class="text-white" />
          </div>
          <div class="ml-3 flex-1">
            <div v-if="currentUser" class="text-sm font-medium text-white">
              {{ currentUser.username }}
            </div>
            <div v-else class="text-sm font-medium text-white">{{ t('notLoggedIn') }}</div>
          </div>
          <ChevronUp
            v-if="currentUser"
            :size="16"
            class="text-white/60 transition-transform duration-200"
            :class="{ 'rotate-180': showUserDropdown }"
          />
        </div>

        <!-- User Dropdown -->
        <div
          v-if="currentUser && showUserDropdown"
          class="mt-2 bg-white/10 backdrop-blur-md rounded-xl border border-white/20 overflow-hidden"
        >
          <div
            @click="handleProfileClick"
            class="flex items-center px-3 py-2 hover:bg-white/10 cursor-pointer transition-colors"
          >
            <UserCircle :size="14" class="text-white/80 mr-3" />
            <span class="text-sm text-white/90">我的资料</span>
          </div>
          <div
            v-if="currentUser.is_root"
            @click="handleUserManagementClick"
            class="flex items-center px-3 py-2 hover:bg-white/10 cursor-pointer transition-colors border-t border-white/10"
          >
            <UserPlus :size="14" class="text-white/80 mr-3" />
            <span class="text-sm text-white/90">{{ t('userManagement') }}</span>
          </div>
          <div
            @click="handleLogout"
            class="flex items-center px-3 py-2 hover:bg-white/10 cursor-pointer transition-colors border-t border-white/10"
          >
            <LogOut :size="14" class="text-white/80 mr-3" />
            <span class="text-sm text-white/90">{{ t('logout') }}</span>
          </div>
        </div>
      </div>

      <!-- Bottom Logo -->
      <div class="px-4 py-2 flex items-center backdrop-blur-sm bg-white/5 border-t border-white/10">
        <img
          class="h-8 w-8 p-0.5 border border-white/30 hover:border-white/50 rounded-lg transition-all"
          src="@/assets/flute_icon.png"
          alt="VidGo"
        />
        <div class="ml-2 flex flex-col">
          <span class="text-sm font-semibold text-white">VidGo</span>
          <span class="text-xs text-white/50">v1.0</span>
        </div>
        <el-tooltip :content="t('hideSidebar')" placement="bottom">
          <button
            @click="toggleCollapse"
            class="ml-auto text-white/60 hover:text-white p-2 rounded-lg hover:bg-white/10 transition-all"
          >
            <LibraryBig :size="20" />
          </button>
        </el-tooltip>
      </div>
    </template>
  </div>

  <!-- Users Dialog Placeholder -->
  <UsersDialog
    v-if="showUsersDialog"
    v-model:visible="showUsersDialog"
    @users-updated="checkUserStatus"
  />

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

.sidebar nav {
  scrollbar-width: thin;
  scrollbar-color: #e5e7eb transparent;
}

.sidebar nav::-webkit-scrollbar {
  width: 6px;
}
.sidebar nav::-webkit-scrollbar-thumb {
  background-color: #e5e7eb;
  border-radius: 3px;
}
.sidebar nav::-webkit-scrollbar-track {
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

.group {
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  background: rgba(255, 255, 255, 0.1);
}

.group:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.25);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
</style>
