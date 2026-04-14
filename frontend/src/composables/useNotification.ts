import { ref, h, render } from 'vue'
import NotificationToast from '@/components/ui/NotificationToast.vue'

export interface NotificationOptions {
  message: string
  type?: 'success' | 'error' | 'warning' | 'info'
  duration?: number
}

type MessageInput =
  | string
  | {
      message: string
      duration?: number
      type?: 'success' | 'error' | 'warning' | 'info'
    }

interface NotificationItem extends NotificationOptions {
  id: string
}

const notifications = ref<NotificationItem[]>([])
let notificationId = 0

let container: HTMLElement | null = null

const ensureContainer = () => {
  if (!container) {
    container = document.createElement('div')
    container.className = 'notification-container'
    container.style.cssText = `
      position: fixed;
      top: 20px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 9999;
      display: flex;
      flex-direction: column;
      align-items: center;
      pointer-events: none;
    `
    document.body.appendChild(container)
  }
  return container
}

const addNotification = (options: NotificationOptions) => {
  const id = `notification-${++notificationId}`
  const notification: NotificationItem = {
    ...options,
    id,
    type: options.type || 'info',
    duration: options.duration ?? 3000,
  }

  notifications.value.push(notification)

  const vnode = h(NotificationToast, {
    id: notification.id,
    type: notification.type as 'success' | 'error' | 'warning' | 'info',
    message: notification.message,
    duration: notification.duration as number,
    onClose: () => removeNotification(id),
  })

  const wrapper = document.createElement('div')
  wrapper.style.pointerEvents = 'auto'
  ensureContainer().appendChild(wrapper)

  render(vnode, wrapper)

  ;(notification as any)._wrapper = wrapper
}

const normalizeMessageInput = (
  input: MessageInput,
  fallbackType: 'success' | 'error' | 'warning' | 'info',
  fallbackDuration?: number,
): NotificationOptions => {
  if (typeof input === 'string') {
    return {
      message: input,
      type: fallbackType,
      duration: fallbackDuration,
    }
  }

  return {
    message: input.message,
    type: input.type || fallbackType,
    duration: input.duration ?? fallbackDuration,
  }
}

const removeNotification = (id: string) => {
  const index = notifications.value.findIndex(n => n.id === id)
  if (index > -1) {
    const notification = notifications.value[index]
    const wrapper = (notification as any)._wrapper

    setTimeout(() => {
      if (wrapper) {
        render(null, wrapper)
        wrapper.remove()
      }
    }, 300)

    notifications.value.splice(index, 1)
  }
}

const success = (message: string, duration?: number) => {
  addNotification({ message, type: 'success', duration })
}

const error = (message: string, duration?: number) => {
  addNotification({ message, type: 'error', duration: duration || 5000 })
}

const warning = (message: string, duration?: number) => {
  addNotification({ message, type: 'warning', duration })
}

const info = (message: string, duration?: number) => {
  addNotification({ message, type: 'info', duration })
}

export const notification = {
  success,
  error,
  warning,
  info,
  add: addNotification,
}

export const ElMessage = {
  success(input: MessageInput) {
    addNotification(normalizeMessageInput(input, 'success'))
  },
  error(input: MessageInput) {
    addNotification(normalizeMessageInput(input, 'error', 5000))
  },
  warning(input: MessageInput) {
    addNotification(normalizeMessageInput(input, 'warning'))
  },
  info(input: MessageInput) {
    addNotification(normalizeMessageInput(input, 'info'))
  },
}

export const useNotification = () => {
  return notification
}

export default notification
