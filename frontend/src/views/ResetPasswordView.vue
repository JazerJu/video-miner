<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from '@/composables/useNotification'
import { BACKEND } from '@/composables/ConfigAPI'

const route = useRoute()
const router = useRouter()

const token = ref('')
const email = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const resetSuccess = ref(false)
const validParams = ref(true)

// 密码验证规则
const validatePassword = (password: string): { valid: boolean; message: string } => {
  if (password.length < 8) {
    return { valid: false, message: '密码长度至少为8位' }
  }
  if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
    return { valid: false, message: '密码必须包含字母和数字' }
  }
  return { valid: true, message: '' }
}

onMounted(() => {
  // 从 URL 参数中获取 token 和 email
  const routeToken = route.query.token as string
  const routeEmail = route.query.email as string

  if (!routeToken || !routeEmail) {
    validParams.value = false
    ElMessage.error('无效的密码重置链接')
    return
  }

  token.value = routeToken
  email.value = routeEmail
})

const handleSubmit = async () => {
  if (!newPassword.value || !confirmPassword.value) {
    ElMessage.error('请填写所有字段')
    return
  }

  // 验证密码强度
  const validation = validatePassword(newPassword.value)
  if (!validation.valid) {
    ElMessage.error(validation.message)
    return
  }

  // 确认密码匹配
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.error('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    const response = await fetch(`${BACKEND}/api/auth/password/reset/confirm/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: email.value,
        token: token.value,
        new_password: newPassword.value,
      }),
    })

    const data = await response.json()

    if (data.success) {
      resetSuccess.value = true
      ElMessage.success('密码重置成功！')
    } else {
      ElMessage.error(data.error || '密码重置失败，请检查链接是否过期')
    }
  } catch (error) {
    console.error('Password reset error:', error)
    ElMessage.error('网络错误，请稍后重试')
  } finally {
    loading.value = false
  }
}

const goToLogin = () => {
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-900">
    <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-8">
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-gray-800">VideoMiner</h1>
        <p class="text-gray-500 mt-2">{{ resetSuccess ? '重置成功' : '设置新密码' }}</p>
      </div>

      <!-- 无效链接提示 -->
      <div v-if="!validParams && !resetSuccess" class="text-center space-y-6">
        <div class="bg-red-50 border border-red-200 rounded-lg p-4">
          <div class="flex items-center justify-center mb-3">
            <svg class="w-12 h-12 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </div>
          <p class="text-red-700">密码重置链接无效或已过期</p>
          <p class="text-red-600 text-sm mt-2">
            请重新请求密码重置。
          </p>
        </div>

        <button
          @click="router.push('/forgot-password')"
          class="w-full py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium"
        >
          重新请求重置
        </button>
      </div>

      <!-- 重置表单 -->
      <form v-else-if="!resetSuccess" @submit.prevent="handleSubmit" class="space-y-6">
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
          <p class="text-blue-700 text-sm">
            正在为 <strong>{{ email }}</strong> 重置密码
          </p>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">新密码</label>
          <input
            v-model="newPassword"
            type="password"
            class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="请输入新密码（至少8位，包含字母和数字）"
            required
          />
          <p class="text-xs text-gray-500 mt-1">
            密码必须包含至少8个字符，且同时包含字母和数字
          </p>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">确认新密码</label>
          <input
            v-model="confirmPassword"
            type="password"
            class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="请再次输入新密码"
            required
          />
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          <span v-if="loading" class="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></span>
          {{ loading ? '重置中...' : '重置密码' }}
        </button>
      </form>

      <!-- 重置成功 -->
      <div v-else class="space-y-6 text-center">
        <div class="bg-green-50 border border-green-200 rounded-lg p-4">
          <div class="flex items-center justify-center mb-3">
            <svg class="w-12 h-12 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
            </svg>
          </div>
          <p class="text-green-700 font-medium">密码重置成功！</p>
          <p class="text-green-600 text-sm mt-2">
            您现在可以使用新密码登录了。
          </p>
        </div>

        <button
          @click="goToLogin"
          class="w-full py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium"
        >
          前往登录
        </button>
      </div>
    </div>
  </div>
</template>
