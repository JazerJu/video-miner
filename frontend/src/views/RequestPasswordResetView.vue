<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from '@/composables/useNotification'
import { useI18n } from 'vue-i18n'
import { BACKEND } from '@/composables/ConfigAPI'

const router = useRouter()
const { t } = useI18n()

const email = ref('')
const loading = ref(false)
const emailSent = ref(false)

const handleSubmit = async () => {
  if (!email.value.trim()) {
    ElMessage.error('请输入邮箱地址')
    return
  }

  // 简单的邮箱格式验证
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(email.value)) {
    ElMessage.error('请输入有效的邮箱地址')
    return
  }

  loading.value = true
  try {
    const response = await fetch(`${BACKEND}/api/auth/password/reset/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email: email.value.trim() }),
    })

    const data = await response.json()

    if (data.success) {
      emailSent.value = true
      ElMessage.success('重置邮件已发送，请检查您的邮箱')
    } else {
      ElMessage.error(data.error || '发送失败，请稍后重试')
    }
  } catch (error) {
    console.error('Password reset request error:', error)
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
        <p class="text-gray-500 mt-2">{{ emailSent ? '邮件已发送' : '重置密码' }}</p>
      </div>

      <!-- 请求发送表单 -->
      <div v-if="!emailSent" class="space-y-6">
        <p class="text-sm text-gray-600 text-center">
          请输入您的注册邮箱，我们将向您发送密码重置链接。
        </p>

        <form @submit.prevent="handleSubmit" class="space-y-6">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">邮箱地址</label>
            <input
              v-model="email"
              type="email"
              class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="请输入您的邮箱"
              required
            />
          </div>

          <button
            type="submit"
            :disabled="loading"
            class="w-full py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            <span v-if="loading" class="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></span>
            {{ loading ? '发送中...' : '发送重置邮件' }}
          </button>
        </form>

        <div class="text-center">
          <button
            @click="goToLogin"
            class="text-sm text-blue-600 hover:underline"
          >
            返回登录
          </button>
        </div>
      </div>

      <!-- 发送成功提示 -->
      <div v-else class="space-y-6">
        <div class="bg-green-50 border border-green-200 rounded-lg p-4">
          <div class="flex items-center justify-center mb-3">
            <svg class="w-12 h-12 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
            </svg>
          </div>
          <p class="text-green-700 text-center">
            密码重置邮件已发送至 <strong>{{ email }}</strong>
          </p>
          <p class="text-green-600 text-sm text-center mt-2">
            请检查您的邮箱，点击邮件中的链接重置密码。
          </p>
        </div>

        <div class="text-center space-y-3">
          <p class="text-sm text-gray-500">
            没有收到邮件？请检查垃圾邮件文件夹，或
          </p>
          <button
            @click="emailSent = false"
            class="text-blue-600 hover:underline text-sm"
          >
            重新发送
          </button>
        </div>

        <div class="text-center pt-4">
          <button
            @click="goToLogin"
            class="text-blue-600 hover:underline"
          >
            返回登录
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
