import { ref, computed } from 'vue'
import { BACKEND } from '@/composables/ConfigAPI'
import { getCSRFToken } from '@/composables/GetCSRFToken'

export interface User {
  id: number
  username: string
  email: string
  is_root: boolean
  premium_authority: boolean
  is_active: boolean
}

const currentUser = ref<User | null>(null)

export const useUser = () => {
  // Check if user is logged in
  const checkUserStatus = async () => {
    try {
      const response = await fetch(`${BACKEND}/api/auth/profile/`, {
        credentials: 'include',
      })

      if (response.ok) {
        const data = await response.json()
        if (data.success) {
          currentUser.value = data.user
        } else {
          currentUser.value = null
        }
      } else {
        currentUser.value = null
      }
    } catch (error) {
      console.error('Error checking user status:', error)
      currentUser.value = null
    }
  }

  // Computed properties for easy access
  const isLoggedIn = computed(() => currentUser.value !== null)
  const username = computed(() => currentUser.value?.username || 'User')
  const userInitial = computed(() => {
    if (!currentUser.value?.username) return 'U'
    return currentUser.value.username.charAt(0).toUpperCase()
  })
  const isAdmin = computed(() => currentUser.value?.is_root || false)

  // Logout function
  const logout = async () => {
    try {
      const csrf = await getCSRFToken()
      const response = await fetch(`${BACKEND}/api/auth/logout/`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrf,
        },
        credentials: 'include',
      })

      if (response.ok) {
        currentUser.value = null
      }
    } catch (error) {
      console.error('Error logging out:', error)
    }
  }

  return {
    currentUser,
    isLoggedIn,
    username,
    userInitial,
    isAdmin,
    checkUserStatus,
    logout,
  }
}
