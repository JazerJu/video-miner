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

<style>
:root {
  --el-color-primary: #0d9488;
  --el-color-primary-light-3: #2dd4bf;
  --el-color-primary-light-5: #5eead4;
  --el-color-primary-light-7: #99f6e4;
  --el-color-primary-light-8: #ccfbf1;
  --el-color-primary-light-9: #f0fdfa;
  --el-color-primary-dark-2: #0f766e;
}
</style>
