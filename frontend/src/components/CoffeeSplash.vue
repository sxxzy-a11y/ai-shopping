<script setup lang="ts">
import CoffeeLoader from './CoffeeLoader.vue'

withDefaults(defineProps<{ message?: string }>(), {
  message: '正在载入，先喝口咖啡…',
})
</script>

<template>
  <div class="coffee-splash" aria-live="polite">
    <div class="coffee-splash-card">
      <CoffeeLoader :label="message" />
    </div>
  </div>
</template>
