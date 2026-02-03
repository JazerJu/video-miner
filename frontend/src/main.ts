// 应用程序入口点，中文注释帮助理解配置
import '@/assets/main.css'

import { createApp } from 'vue'
import { createI18n } from 'vue-i18n'
import App from '@/App.vue'
import 'video.js/dist/video-js.css'
import './assets/tailwind.css'
import '@/assets/vjs-luxmty/vjs-luxmty.css'

import router from '@/router'
import en from '@/locales/en'
import zh from '@/locales/zh'

import ElementPlus from 'element-plus'
import enEl from 'element-plus/es/locale/lang/en'
import zhEl from 'element-plus/es/locale/lang/zh-cn'
import { notification } from '@/composables/useNotification'

import 'element-plus/dist/index.css'
import '@/assets/tailwind.css' // <-  if you keep Tailwind

// 全局处理未捕获的 Promise 错误（API 调用失败时的正常现象）
window.addEventListener('unhandledrejection', (event) => {
  console.warn('API request failed (this is normal in static mode):', event.reason)
  event.preventDefault() // 防止应用崩溃
})

// 全局处理 JavaScript 错误，提高应用稳定性
window.addEventListener('error', (event) => {
  console.warn('JavaScript error:', event.error)
  event.preventDefault()
})

// 创建国际化实例，支持中英双语切换
const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('lang') || 'en', // 默认语言为英语
  fallbackLocale: 'zh', // 回退语言为中文
  messages: { en, zh },
})

const app = createApp(App)

// Vue 应用级错误处理，避免未捕获错误导致应用崩溃
app.config.errorHandler = (err, instance, info) => {
  console.warn('Vue error:', err, info)
}

// 注册各种插件
app.use(i18n)
app.use(ElementPlus, { locale: i18n.global.locale.value === 'zh' ? zhEl : enEl })
app.use(router)

app.config.globalProperties.$notify = notification
app.provide('notification', notification)

// 挂载应用并暴露到全局，方便调试和外部访问
const vueApp = app.mount('#app')
;(window as any).vueApp = vueApp
