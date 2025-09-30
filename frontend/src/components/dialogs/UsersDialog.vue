<template>
  <div
    v-if="visible"
    class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    @click.self="closeDialog"
  >
    <div class="bg-white rounded-lg shadow-xl w-[900px] h-[700px] flex overflow-hidden">
      <!-- Left Sidebar -->
      <div class="w-48 bg-gray-50 border-r border-gray-200">
        <div class="p-4">
          <h2 class="text-lg font-semibold text-gray-800 mb-4">用户管理</h2>
          <nav class="space-y-2">
            <button
              @click="activeTab = 'users'"
              :class="[
                'w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors',
                activeTab === 'users'
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-700 hover:bg-gray-200',
              ]"
            >
              用户列表
            </button>
            <button
              @click="activeTab = 'create'"
              :class="[
                'w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors',
                activeTab === 'create'
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-700 hover:bg-gray-200',
              ]"
            >
              创建用户
            </button>
          </nav>
        </div>
      </div>

      <!-- Main Content -->
      <div class="flex-1 flex flex-col">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-800">
            {{ activeTab === 'users' ? '用户列表' : '创建用户' }}
          </h3>
          <button @click="closeDialog" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              ></path>
            </svg>
          </button>
        </div>

        <!-- Content Area -->
        <div class="flex-1 p-6 overflow-y-auto">
          <!-- Loading overlay -->
          <div
            v-if="loading"
            class="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-10"
          >
            <div class="flex items-center space-x-2">
              <div
                class="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"
              ></div>
              <span class="text-gray-600">加载中...</span>
            </div>
          </div>

          <!-- Users List Tab -->
          <div v-if="activeTab === 'users'" class="space-y-4">
            <div class="flex justify-between items-center mb-4">
              <h4 class="text-lg font-medium text-gray-800">用户列表 ({{ users.length }})</h4>
              <button
                @click="fetchUsers"
                class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
              >
                刷新
              </button>
            </div>

            <div class="bg-white border rounded-lg overflow-hidden">
              <table class="w-full">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-4 py-3 text-left text-sm font-medium text-gray-700">用户名</th>
                    <th class="px-4 py-3 text-left text-sm font-medium text-gray-700">邮箱</th>
                    <th class="px-4 py-3 text-left text-sm font-medium text-gray-700">类型</th>
                    <th class="px-4 py-3 text-left text-sm font-medium text-gray-700">权限</th>
                    <th class="px-4 py-3 text-left text-sm font-medium text-gray-700">状态</th>
                    <th class="px-4 py-3 text-left text-sm font-medium text-gray-700">创建时间</th>
                    <th class="px-4 py-3 text-left text-sm font-medium text-gray-700">操作</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-200">
                  <tr v-for="user in users" :key="user.id" class="hover:bg-gray-50">
                    <td class="px-4 py-3 text-sm text-gray-900">{{ user.username }}</td>
                    <td class="px-4 py-3 text-sm text-gray-900">{{ user.email || '-' }}</td>
                    <td class="px-4 py-3 text-sm">
                      <span
                        v-if="user.is_root"
                        class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-red-100 text-red-800"
                      >
                        管理员
                      </span>
                      <span
                        v-else
                        class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800"
                      >
                        普通用户
                      </span>
                    </td>
                    <td class="px-4 py-3 text-sm">
                      <span
                        v-if="user.premium_authority"
                        class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800"
                      >
                        高级权限
                      </span>
                      <span
                        v-else
                        class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-gray-100 text-gray-800"
                      >
                        基础权限
                      </span>
                    </td>
                    <td class="px-4 py-3 text-sm">
                      <span
                        v-if="user.is_active"
                        class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800"
                      >
                        活跃
                      </span>
                      <span
                        v-else
                        class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-red-100 text-red-800"
                      >
                        禁用
                      </span>
                    </td>
                    <td class="px-4 py-3 text-sm text-gray-900">
                      {{ new Date(user.created_at).toLocaleDateString() }}
                    </td>
                    <td class="px-4 py-3 text-sm">
                      <button
                        v-if="!user.is_root"
                        @click="editUser(user)"
                        class="text-blue-600 hover:text-blue-800 mr-3"
                      >
                        编辑
                      </button>
                    </td>
                  </tr>
                  <tr v-if="users.length === 0">
                    <td colspan="7" class="px-4 py-8 text-center text-gray-500">暂无用户数据</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Create User Tab -->
          <div v-if="activeTab === 'create'" class="space-y-6">
            <form @submit.prevent="createUser" class="space-y-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">用户名</label>
                <input
                  v-model="newUser.username"
                  type="text"
                  class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="输入用户名"
                  required
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">密码</label>
                <input
                  v-model="newUser.password"
                  type="password"
                  class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="输入密码"
                  required
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">邮箱（可选）</label>
                <input
                  v-model="newUser.email"
                  type="email"
                  class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="输入邮箱"
                />
              </div>

              <div>
                <label class="flex items-center space-x-2 text-sm font-medium text-gray-700">
                  <input
                    v-model="newUser.premium_authority"
                    type="checkbox"
                    class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>高级权限</span>
                </label>
              </div>

              <div v-if="categories.length > 0">
                <label class="block text-sm font-medium text-gray-700 mb-2">隐藏分类</label>
                <div class="relative">
                  <el-select
                    v-model="newUser.hidden_categories"
                    multiple
                    collapse-tags
                    collapse-tags-tooltip
                    placeholder="选择要对该用户隐藏的分类"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="category in categories"
                      :key="category.id"
                      :label="category.name"
                      :value="category.id"
                    />
                  </el-select>
                </div>
                <p class="mt-2 text-sm text-gray-500">选中的分类将对该用户隐藏</p>
              </div>

              <div class="pt-4">
                <button
                  type="submit"
                  class="w-full px-4 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                >
                  创建用户
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Edit User Dialog -->
  <div
    v-if="showEditDialog && editingUser"
    class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-60"
    @click.self="showEditDialog = false"
  >
    <div class="bg-white rounded-lg shadow-xl w-96 p-6">
      <h2 class="text-xl font-bold text-gray-800 mb-4">编辑用户</h2>
      <form @submit.prevent="updateUser" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">用户名</label>
          <input
            :value="editingUser.username"
            type="text"
            class="w-full p-3 border border-gray-300 rounded-md bg-gray-100"
            readonly
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
          <input
            v-model="editingUser.email"
            type="email"
            class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="输入邮箱"
          />
        </div>

        <div>
          <label class="flex items-center space-x-2 text-sm font-medium text-gray-700">
            <input
              v-model="editingUser.premium_authority"
              type="checkbox"
              class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span>高级权限</span>
          </label>
        </div>

        <div>
          <label class="flex items-center space-x-2 text-sm font-medium text-gray-700">
            <input
              v-model="editingUser.is_active"
              type="checkbox"
              class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span>账户活跃</span>
          </label>
        </div>

        <div v-if="categories.length > 0">
          <label class="block text-sm font-medium text-gray-700 mb-2">隐藏分类</label>
          <div class="relative">
            <el-select
              v-model="editingUser.hidden_categories"
              multiple
              collapse-tags
              collapse-tags-tooltip
              placeholder="选择要对该用户隐藏的分类"
              style="width: 100%"
            >
              <el-option
                v-for="category in categories"
                :key="category.id"
                :label="category.name"
                :value="category.id"
              />
            </el-select>
          </div>
        </div>

        <div class="flex space-x-3 pt-4">
          <button
            type="button"
            @click="showEditDialog = false"
            class="flex-1 px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
          >
            取消
          </button>
          <button
            type="submit"
            class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            更新
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElSelect, ElOption } from 'element-plus'
import { getCSRFToken } from '@/composables/GetCSRFToken'

interface User {
  id: string
  username: string
  email: string
  is_root: boolean
  premium_authority: boolean
  is_active: boolean
  created_at: string
  hidden_categories: string[]
}

interface Category {
  id: string
  name: string
}

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void
  (e: 'users-updated'): void
}>()

// Component state
const activeTab = ref('users')
const loading = ref(false)
const users = ref<User[]>([])
const categories = ref<Category[]>([])
const showEditDialog = ref(false)
const editingUser = ref<User | null>(null)

// New user form
const newUser = ref({
  username: '',
  password: '',
  email: '',
  premium_authority: false,
  hidden_categories: [],
})

import { BACKEND } from '@/composables/ConfigAPI'

// Fetch users list
const fetchUsers = async () => {
  loading.value = true
  try {
    const response = await fetch(`${BACKEND}/api/auth/list-users/`, {
      credentials: 'include',
    })

    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        users.value = data.users
      } else {
        ElMessage.error(data.error || '获取用户列表失败')
      }
    } else {
      ElMessage.error('获取用户列表失败')
    }
  } catch (error) {
    console.error('Error fetching users:', error)
    ElMessage.error('网络错误，请重试')
  } finally {
    loading.value = false
  }
}

// Fetch categories for hidden categories selection
const fetchCategories = async () => {
  try {
    const response = await fetch(`${BACKEND}/api/category/query/0`)
    if (response.ok) {
      const data = await response.json()
      categories.value = data.categories || []
    }
  } catch (error) {
    console.error('Error fetching categories:', error)
  }
}

// Create new user
const createUser = async () => {
  if (!newUser.value.username || !newUser.value.password) {
    ElMessage.error('请填写用户名和密码')
    return
  }

  loading.value = true
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/auth/create-user/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify(newUser.value),
    })

    const data = await response.json()

    if (data.success) {
      ElMessage.success('用户创建成功')
      newUser.value = {
        username: '',
        password: '',
        email: '',
        premium_authority: false,
        hidden_categories: [],
      }
      fetchUsers()
      activeTab.value = 'users'
    } else {
      ElMessage.error(data.error || '创建用户失败')
    }
  } catch (error) {
    console.error('Error creating user:', error)
    ElMessage.error('网络错误，请重试')
  } finally {
    loading.value = false
  }
}

// Edit user
const editUser = (user: User) => {
  editingUser.value = { ...user }
  showEditDialog.value = true
}

// Update user
const updateUser = async () => {
  if (!editingUser.value) return

  loading.value = true
  try {
    const csrf = await getCSRFToken()
    const response = await fetch(`${BACKEND}/api/auth/update-user/${editingUser.value.id}/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      credentials: 'include',
      body: JSON.stringify({
        email: editingUser.value.email,
        premium_authority: editingUser.value.premium_authority,
        hidden_categories: editingUser.value.hidden_categories,
        is_active: editingUser.value.is_active,
      }),
    })

    const data = await response.json()

    if (data.success) {
      ElMessage.success('用户更新成功')
      showEditDialog.value = false
      fetchUsers()
    } else {
      ElMessage.error(data.error || '更新用户失败')
    }
  } catch (error) {
    console.error('Error updating user:', error)
    ElMessage.error('网络错误，请重试')
  } finally {
    loading.value = false
  }
}

// Close dialog
const closeDialog = () => {
  emit('update:visible', false)
}

// Initialize data
onMounted(() => {
  fetchUsers()
  fetchCategories()
})
</script>

<style scoped>
/* Additional custom styles if needed */
</style>
