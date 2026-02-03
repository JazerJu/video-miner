<template>
  <div
    v-if="visible"
    class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
    @click.self="closeDialog"
  >
    <div class="bg-white rounded-lg shadow-xl w-[500px] max-h-[80vh] flex flex-col overflow-hidden">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-gray-200">
        <h3 class="text-lg font-semibold text-gray-800">我的资料</h3>
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

      <!-- Content -->
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

        <!-- User Info -->
        <div class="space-y-6">
          <div class="bg-gray-50 rounded-lg p-4">
            <div class="flex items-center space-x-4">
              <div
                class="w-16 h-16 rounded-full bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center"
              >
                <User :size="32" class="text-white" />
              </div>
              <div>
                <div class="text-lg font-medium text-gray-800">{{ user?.username }}</div>
                <div class="text-sm text-gray-500">
                  {{ user?.is_root ? '管理员' : user?.premium_authority ? '高级用户' : '普通用户' }}
                </div>
              </div>
            </div>
          </div>

          <!-- Email Section -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">邮箱</label>
            <div class="flex items-center space-x-2">
              <input
                v-model="email"
                type="email"
                class="flex-1 p-2 border border-gray-300 rounded-md"
                placeholder="输入邮箱地址"
              />
              <button
                @click="updateEmail"
                :disabled="saving"
                class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
              >
                {{ saving ? '保存中...' : '更新' }}
              </button>
            </div>
          </div>

          <!-- Password Reset Section -->
          <div class="border-t pt-4">
            <h4 class="text-md font-medium text-gray-800 mb-4">密码管理</h4>
            <div v-if="!resetEmailSent">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">邮箱地址</label>
                <div class="flex items-center space-x-2">
                  <input
                    v-model="resetEmail"
                    type="email"
                    class="flex-1 p-2 border border-gray-300 rounded-md"
                    :placeholder="user?.email || '输入您的邮箱地址'"
                  />
                  <button
                    @click="requestPasswordReset"
                    :disabled="sendingResetEmail"
                    class="px-4 py-2 bg-yellow-500 text-white rounded hover:bg-yellow-600 disabled:opacity-50"
                  >
                    {{ sendingResetEmail ? '发送中...' : '发送重置邮件' }}
                  </button>
                </div>
                <p class="mt-2 text-sm text-gray-500">
                  我们将向您的邮箱发送一封包含重置链接的邮件。
                </p>
              </div>
            </div>
            <div v-else class="bg-green-50 border border-green-200 rounded-lg p-4">
              <div class="flex items-center">
                <svg class="w-5 h-5 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <span class="text-green-700">重置邮件已发送！请检查您的邮箱。</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="flex justify-end p-4 border-t border-gray-200 bg-gray-50">
        <button
          @click="closeDialog"
          class="px-4 py-2 text-gray-600 hover:text-gray-800"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { User } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { BACKEND } from '@/composables/ConfigAPI'

interface User {
  id: number
  username: string
  email: string
  is_root: boolean
  premium_authority: boolean
  is_active: boolean
}

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'profile-updated'): void
}>()

const loading = ref(false)
const saving = ref(false)
const sendingResetEmail = ref(false)
const resetEmailSent = ref(false)
const user = ref<User | null>(null)
const email = ref('')
const resetEmail = ref('')

const fetchProfile = async () => {
  try {
    loading.value = true
    const response = await fetch(`${BACKEND}/api/auth/profile/`, {
      credentials: 'include',
    })
    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        user.value = data.user
        email.value = data.user.email
        resetEmail.value = data.user.email
      }
    }
  } catch (error) {
    console.error('Error fetching profile:', error)
    ElMessage.error('加载资料失败')
  } finally {
    loading.value = false
  }
}

const updateEmail = async () => {
  if (!email.value.trim()) {
    ElMessage.warning('请输入邮箱地址')
    return
  }

  try {
    saving.value = true
    const response = await fetch(`${BACKEND}/api/auth/profile/`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ email: email.value }),
    })

    const data = await response.json()

    if (data.success) {
      ElMessage.success('邮箱更新成功')
      user.value = data.user
    } else {
      ElMessage.error(data.error || '更新失败')
    }
  } catch (error) {
    console.error('Error updating email:', error)
    ElMessage.error('更新失败')
  } finally {
    saving.value = false
  }
}

const requestPasswordReset = async () => {
  if (!resetEmail.value.trim()) {
    ElMessage.warning('请输入邮箱地址')
    return
  }

  try {
    sendingResetEmail.value = true
    const response = await fetch(`${BACKEND}/api/auth/password/reset/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ email: resetEmail.value }),
    })

    const data = await response.json()

    if (data.success) {
      resetEmailSent.value = true
      ElMessage.success('重置邮件已发送')
    } else {
      ElMessage.error(data.error || '发送失败')
    }
  } catch (error) {
    console.error('Error requesting password reset:', error)
    ElMessage.error('发送失败')
  } finally {
    sendingResetEmail.value = false
  }
}

const closeDialog = () => {
  emit('update:visible', false)
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    fetchProfile()
    resetEmailSent.value = false
  }
})
</script>
