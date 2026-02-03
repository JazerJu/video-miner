import { createRouter, createWebHistory } from 'vue-router'

// 路由配置：定义应用的页面路由和参数传递规则
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },

    // 流媒体视频播放路由：/watch/stream/foo.mp4 用于HLS播放
    {
      path: '/watch/stream/:basename([^/]+?)\\.:ext(mp4|webm|mkv|m4a|mp3|wav|aac)',
      name: 'watch-stream-video',
      component: () => import('@/views/WatchVideo.vue'),
      props: (route) => ({
        basename: route.params.basename as string,
        ext: route.params.ext as string,
        stream: true, // 标识为流媒体模式
      }),
    },

    // 普通视频播放路由：/watch/foo.mp4 用于常规播放
    {
      path: '/watch/:basename([^/]+)\\.:ext(mp4|webm|mkv|m4a|mp3|wav|aac)',
      name: 'watch-video',
      component: () => import('@/views/WatchVideo.vue'),
      props: (route) => ({
        basename: route.params.basename as string,
        ext: route.params.ext as string,
        stream: false, // 标识为普通播放模式
      }),
    },

    // 字幕编辑器路由：/editor/foo.mp4
    {
      path: '/editor/:basename([^/]+)\\.:ext(mp4|webm|mkv|m4a|mp3|wav|aac)',
      name: 'subtitle-editor',
      component: () => import('@/views/SubtitleEditorView.vue'),
      props: (route) => {
        const { basename, ext } = route.params as { basename: string; ext: string }
        return { basename, ext }
      },
    },

    // 波形测试页面（开发调试用）
    {
      path: '/waveform-test',
      name: 'waveform-test',
      component: () => import('@/views/waveform_test.vue'),
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },

    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: () => import('@/views/RequestPasswordResetView.vue'),
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('@/views/ResetPasswordView.vue'),
    },
  ],
})

export default router
