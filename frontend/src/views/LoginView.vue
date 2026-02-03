<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { BACKEND } from '@/composables/ConfigAPI'

const router = useRouter()
const { t } = useI18n()

type Mode = 'login' | 'register' | 'rootRegister'
const mode = ref<Mode>('login')
const loading = ref(false)

const form = ref({
  username: '',
  password: '',
  email: '',
})

const emailError = ref('')

const validateEmail = (email: string): boolean => {
  if (!email) {
    emailError.value = t('emailRequired')
    return false
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(email)) {
    emailError.value = t('emailInvalid')
    return false
  }
  emailError.value = ''
  return true
}

const checkRootExists = async () => {
  try {
    const response = await fetch(`${BACKEND}/api/auth/check-root/`)
    const data = await response.json()
    if (!data.root_exists) {
      mode.value = 'rootRegister'
    }
  } catch (error) {
    console.error('Error checking root status:', error)
  }
}

const handleSubmit = async () => {
  if (!form.value.username || !form.value.password) {
    ElMessage.error(t('pleaseEnterUsername'))
    return
  }

  if (mode.value === 'register' && !validateEmail(form.value.email)) {
    ElMessage.error(emailError.value)
    return
  }

  loading.value = true
  try {
    let endpoint = `${BACKEND}/api/auth/login/`
    if (mode.value === 'register') {
      endpoint = `${BACKEND}/api/auth/register/`
    } else if (mode.value === 'rootRegister') {
      endpoint = `${BACKEND}/api/auth/register-root/`
    }

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(form.value),
    })

    const data = await response.json()

    if (data.success) {
      ElMessage.success(
        mode.value === 'login' ? t('loginSuccess') : t('registerSuccess')
      )
      router.push('/')
    } else {
      ElMessage.error(data.error || t('operationFailed'))
    }
  } catch (error) {
    console.error('Auth error:', error)
    ElMessage.error(t('networkError'))
  } finally {
    loading.value = false
  }
}

const switchMode = (newMode: Mode) => {
  mode.value = newMode
  emailError.value = ''
}

const getTitle = () => {
  if (mode.value === 'rootRegister') return t('createRootUser')
  if (mode.value === 'register') return t('registerAccount')
  return t('login')
}

const getSubmitText = () => {
  if (mode.value === 'rootRegister') return t('create')
  if (mode.value === 'register') return t('register')
  return t('login')
}

onMounted(() => {
  checkRootExists()
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-900">
    <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-8">
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-gray-800">VidGo</h1>
        <p class="text-gray-500 mt-2">{{ getTitle() }}</p>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-6">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('username') }}</label>
          <input
            v-model="form.username"
            type="text"
            class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            :placeholder="t('pleaseEnterUsername')"
            required
          />
        </div>

        <div v-if="mode === 'register'">
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('email') }}</label>
          <input
            v-model="form.email"
            type="email"
            class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            :placeholder="t('pleaseEnterEmail')"
            :class="{ 'border-red-500': emailError }"
            required
          />
          <p v-if="emailError" class="text-xs text-red-500 mt-1">{{ emailError }}</p>
        </div>

        <div v-if="mode === 'rootRegister'">
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('emailOptional') }}</label>
          <input
            v-model="form.email"
            type="email"
            class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            :placeholder="t('pleaseEnterEmail')"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('password') }}</label>
          <input
            v-model="form.password"
            type="password"
            class="w-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            :placeholder="t('pleaseEnterPassword')"
            required
          />
          <p v-if="mode !== 'login'" class="text-xs text-gray-500 mt-1">
            {{ t('passwordRequirement') }}
          </p>
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          <span
            v-if="loading"
            class="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"
          ></span>
          {{ getSubmitText() }}
        </button>
      </form>

      <div class="mt-6 text-center text-sm">
        <div v-if="mode === 'login'" class="space-y-2">
          <button @click="switchMode('register')" class="text-blue-600 hover:underline block w-full">
            {{ t('noAccount') }} {{ t('registerNow') }}
          </button>
          <button @click="router.push('/forgot-password')" class="text-gray-600 hover:underline block w-full">
            {{ t('forgotPassword') }}
          </button>
          <button @click="router.push('/')" class="text-gray-600 hover:text-gray-800">
            {{ t('returnTo') }} {{ t('home') }}
          </button>
        </div>

        <div v-else-if="mode === 'register'" class="space-y-2">
          <button @click="switchMode('login')" class="text-blue-600 hover:underline block w-full">
            {{ t('hasAccount') }} {{ t('loginNow') }}
          </button>
          <button @click="router.push('/')" class="text-gray-600 hover:text-gray-800">
            {{ t('returnTo') }} {{ t('home') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
