<!-- 根组件 -->
<script setup lang="ts">
import Dashboard from './components/Home/Home.vue'
import { RouterView } from 'vue-router'
import TopProgress from './components/ui/TopProgress.vue'
</script>
<template>
  <TopProgress />
  <RouterView />
</template>
