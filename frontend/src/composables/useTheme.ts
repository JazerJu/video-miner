import { ref, watch } from 'vue'

export type Theme = 'dark' | 'light'

const readStoredTheme = (): Theme => {
  if (typeof window === 'undefined') return 'dark'

  return localStorage.getItem('theme') === 'light' ? 'light' : 'dark'
}

export const theme = ref<Theme>(readStoredTheme())

const applyThemeClass = (value: Theme) => {
  if (typeof document === 'undefined') return

  document.documentElement.classList.remove('dark', 'light')
  document.documentElement.classList.add(value)
  document.body.style.backgroundColor = value === 'dark' ? '#0f172a' : '#f8fafc'
}

applyThemeClass(theme.value)

watch(theme, (value) => {
  applyThemeClass(value)
  localStorage.setItem('theme', value)
})

export const toggleTheme = () => {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
}

export function useTheme() {
  return {
    theme,
    toggleTheme,
  }
}
