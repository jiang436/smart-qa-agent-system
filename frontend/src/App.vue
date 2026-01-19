<script setup lang="ts">
import { RouterView } from 'vue-router'
import Sidebar from '@/components/Sidebar.vue'
</script>

<template>
  <div class="flex h-screen overflow-hidden">
    <Sidebar />
    <main class="flex-1 overflow-hidden">
      <RouterView />
    </main>
  </div>
</template>
