import { ref } from 'vue'

export interface UploadTask {
  id: number
  name: string
  progress: number
  status: 'uploading' | 'success' | 'error'
}

/**
 * 全局上传任务状态（模块级 ref 单例）。
 * StreamMediaCard 写入，TasksView 读取，同一进程共享同一份 ref。
 */
const uploadTasks = ref<UploadTask[]>([])
let idCounter = 0

export function useUploadTasks() {
  const addTask = (name: string): number => {
    const id = ++idCounter
    uploadTasks.value.push({ id, name, progress: 0, status: 'uploading' })
    return id
  }

  const updateProgress = (id: number, progress: number) => {
    const task = uploadTasks.value.find((t) => t.id === id)
    if (task) task.progress = progress
  }

  const markSuccess = (id: number) => {
    const task = uploadTasks.value.find((t) => t.id === id)
    if (task) task.status = 'success'
  }

  const markError = (id: number) => {
    const task = uploadTasks.value.find((t) => t.id === id)
    if (task) task.status = 'error'
  }

  /** 移除所有已完成 / 失败的任务 */
  const clearFinished = () => {
    uploadTasks.value = uploadTasks.value.filter((t) => t.status === 'uploading')
  }

  /** 当前是否仍有上传中的任务 */
  const hasUploading = () => uploadTasks.value.some((t) => t.status === 'uploading')

  return {
    uploadTasks,
    addTask,
    updateProgress,
    markSuccess,
    markError,
    clearFinished,
    hasUploading,
  }
}
