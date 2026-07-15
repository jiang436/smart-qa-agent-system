<script setup lang="ts">
import { RouterView } from 'vue-router'
import Sidebar from '@/components/Sidebar.vue'
</script>

<template>
  <div class="grid grid-cols-[auto_1fr] h-[100dvh] overflow-hidden bg-bg-primary">
    <Sidebar />
    <main class="overflow-hidden flex flex-col">
      <RouterView v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
.page-enter-active { animation: slideUp 0.2s ease-out; }
.page-leave-active { animation: fadeIn 0.15s ease-in reverse; }
</style>
